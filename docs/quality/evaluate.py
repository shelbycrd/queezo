"""Evaluate production distractor generation and fallback on synthetic cards."""
import argparse
import asyncio
import hashlib
import json
import os
import random
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
from app.database import init_database, make_engine
from app.models import Deck, Flashcard, FlashcardDistractorSource, User
from app.services import distractor_cache as cache, distractors as ai


ARMS = ("ai_only", "hybrid_policy", "deck_only")


def read_dataset(path):
    data = path.read_bytes()
    decks = json.loads(data)["decks"]
    ids = [deck["id"] for deck in decks]
    if len(ids) != len(set(ids)) or any(not deck["cards"] for deck in decks):
        raise ValueError("Decks must be nonempty and have unique IDs.")
    records = [
        {"id": f"{deck['id']}-{index:02}", "category": deck["category"], "deck": deck["id"],
         "front": front, "back": back}
        for deck in decks for index, (front, back) in enumerate(deck["cards"], 1)
    ]
    if any(not card["front"].strip() or not card["back"].strip() for card in records):
        raise ValueError("Synthetic cards must have two nonblank sides.")
    return records, hashlib.sha256(data).hexdigest()


def make_fixture(card, index):
    """Script transport failures and candidate mixtures independently of the model."""
    back = card["back"]
    length = ai._literal_length(card["front"], back)
    if length:
        alternatives = [letter + back.strip()[1:] for letter in "bcfmpvxyz" if letter != back.strip()[0]]
    else:
        alternatives = [f"Mock choice {n}" for n in range(1, 7)]
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        bucket = index % 6
        contamination = [back.upper(), alternatives[0], alternatives[0].upper(), "", None]
        if bucket == 5:
            raise httpx.ConnectError("Fixture outage", request=request)
        if bucket == 4 and calls == 1:
            raise httpx.ReadTimeout("Fixture timeout", request=request)
        if bucket == 3 or (bucket == 1 and calls == 2):
            content = "Invalid JSON fixture"
        else:
            candidates = {
                0: [*contamination, *alternatives[1:4]],
                1: contamination if calls == 1 else alternatives[1:4],
                2: contamination,
                4: [*contamination, alternatives[1]],
            }[bucket]
            if bucket == 1 and calls == 1:
                candidates = [*candidates, "\ud800"]
            content = json.dumps({"distractors": candidates})
        return httpx.Response(200, json={"message": {"content": content}})

    return respond


class SeededTransport(httpx.AsyncBaseTransport):
    """Set a benchmark-only Ollama seed while preserving production request options."""
    def __init__(self, seed):
        self.seed = seed
        self.delegate = httpx.AsyncHTTPTransport(trust_env=False)

    async def handle_async_request(self, request):
        payload = json.loads(request.content)
        payload["options"]["seed"] = self.seed
        headers = [(name, value) for name, value in request.headers.multi_items()
                   if name != "content-length"]
        seeded = httpx.Request(request.method, request.url, headers=headers, json=payload,
                               extensions=request.extensions)
        return await self.delegate.handle_async_request(seeded)

    async def aclose(self):
        await self.delegate.aclose()


async def generate(card, index, mode, seed):
    trace = []
    parse, collect = ai._parse_candidates, ai._collect_candidates

    async def request_sent(request):
        prompt = json.loads(request.content)["messages"][0]["content"]
        trace.append({"strategy": "literal" if ai.STRING_PROMPT in prompt else "conceptual"})

    async def headers_received(response):
        trace[-1]["status_code"] = response.status_code

    def traced_parse(response):
        try:
            return parse(response)
        except ai.DistractorGenerationError:
            trace[-1]["invalid_response"] = True
            raise

    def traced_collect(candidates, correct, accepted, rejected, length):
        before = len(accepted)
        counts = collect(candidates, correct, accepted, rejected, length)
        trace[-1].update(candidates=len(candidates), accepted=len(accepted) - before, rejected=dict(counts))
        return counts

    transport = (SeededTransport(seed + index) if mode == "live"
                 else httpx.MockTransport(make_fixture(card, index)))
    async with httpx.AsyncClient(transport=transport, trust_env=False, event_hooks={
        "request": [request_sent], "response": [headers_received],
    }) as client:
        with patch.object(ai, "_parse_candidates", traced_parse), patch.object(ai, "_collect_candidates", traced_collect):
            try:
                choices = await ai.generate_distractors(card["front"], card["back"], client=client)
            except ai.DistractorGenerationError as error:
                return {"status": error.reason, "choices": list(error.candidates), "attempts": trace}
    return {"status": "ready", "choices": choices, "attempts": trace}


def seed_sqlite(factory, records):
    id_map = {}
    with factory.begin() as db:
        owner = User(email="distractor-qa@example.com", password_hash="not-used")
        db.add(owner)
        db.flush()
        for arm in ARMS[1:]:
            decks = {}
            for card in records:
                if card["deck"] not in decks:
                    deck = Deck(owner_id=owner.id, title=f"{arm} {card['deck']}")
                    db.add(deck)
                    db.flush()
                    decks[card["deck"]] = deck.id
                row = Flashcard(deck_id=decks[card["deck"]], front=card["front"], back=card["back"])
                db.add(row)
                db.flush()
                id_map[arm, card["id"]] = row.id
    return owner, id_map


async def evaluate_fallback(factory, card_id, owner, generation):
    calls = 0

    async def replay(front, back, *, model):
        nonlocal calls
        calls += 1
        if generation["status"] == "ready":
            return generation["choices"]
        raise ai.DistractorGenerationError("Benchmark replay", candidates=generation["choices"],
                                           reason=generation["status"])

    with patch.object(ai, "generate_distractors", replay):
        try:
            choices = await cache.get_or_generate_distractors(card_id, owner)
        except cache.InsufficientDistractorsError as error:
            assert calls == 1
            return {"status": error.reason, "choices": []}
        # The follow-up must be a cache hit. It must not borrow the other arm's entry.
        assert await cache.get_or_generate_distractors(card_id, owner) == choices
    assert calls == 1
    with factory() as db:
        deck_positions = set(db.scalars(select(FlashcardDistractorSource.position).where(
            FlashcardDistractorSource.flashcard_id == card_id,
        )))
    return {"status": "ready", "choices": choices,
            "origins": ["deck" if pos in deck_positions else "ai" for pos in range(len(choices))]}


def summarize(results):
    request_count = sum(len(row["ai_only"]["attempts"]) for row in results)
    attempts = [attempt for row in results for attempt in row["ai_only"]["attempts"]]
    rejections = Counter()
    for attempt in attempts:
        rejections.update(attempt.get("rejected", {}))
    totals = {
        "cards": len(results),
        "requests": request_count,
        "retry_requests": sum(max(0, len(row["ai_only"]["attempts"]) - 1) for row in results),
        "cards_retried": sum(len(row["ai_only"]["attempts"]) > 1 for row in results),
        "literal_retry_requests": sum(attempt["strategy"] == "literal" for attempt in attempts),
        "invalid_responses": sum(attempt.get("invalid_response", False) for attempt in attempts),
        "requests_without_response_headers": sum("status_code" not in attempt for attempt in attempts),
        "http_failure_responses": sum(not 200 <= attempt.get("status_code", 200) < 300 for attempt in attempts),
        "candidates_received": sum(attempt.get("candidates", 0) for attempt in attempts),
        "rejected_candidates": dict(sorted(rejections.items())),
        "cards_with_duplicates": sum(any(a.get("rejected", {}).get("duplicate") for a in row["ai_only"]["attempts"])
                                     for row in results),
        "cards_with_correct_contamination": sum(any(a.get("rejected", {}).get("correct_answer")
                                                   for a in row["ai_only"]["attempts"]) for row in results),
    }
    for arm in ARMS:
        statuses = Counter(row[arm]["status"] for row in results)
        ready = statuses.get("ready", 0)
        totals[arm] = {"ready": ready, "success_rate": round(ready / len(results), 4),
                       "statuses": dict(sorted(statuses.items()))}
        if arm != "ai_only":
            # All failed fallback calls lacked three combined choices. The status is the model outcome.
            totals[arm]["combined_shortfalls"] = len(results) - ready
    origins = Counter()
    for row in results:
        if row["hybrid_policy"]["status"] == "ready":
            labels = set(row["hybrid_policy"]["origins"])
            name = "mixed" if len(labels) == 2 else labels.pop() + "_only"
            origins[name] += 1
    totals["hybrid_policy"]["origin_mix"] = dict(sorted(origins.items()))
    return totals


def live_metadata():
    base_url = os.getenv("OLLAMA_BASE_URL", ai.DEFAULT_BASE_URL).rstrip("/")
    url = urlparse(base_url)
    local_names = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
    if url.scheme not in {"http", "https"} or url.hostname not in local_names or url.username:
        raise ValueError("This benchmark accepts a local Ollama endpoint only.")
    with httpx.Client(timeout=5, trust_env=False) as client:
        version = client.get(base_url + "/api/version").raise_for_status().json()["version"]
        models = client.get(base_url + "/api/tags").raise_for_status().json()["models"]
    installed = next((entry for entry in models if entry["name"] == ai.configured_model()), None)
    if installed is None:
        raise ValueError("The configured model is not installed on the local Ollama server.")
    return {"ollama_version": version, "model_digest": installed["digest"]}


async def run(records, args):
    results = []
    with TemporaryDirectory(prefix="queezo-quality-") as directory:
        engine = make_engine(f"sqlite:///{(Path(directory) / 'quality.db').as_posix()}")
        try:
            init_database(engine)
            factory = sessionmaker(bind=engine, expire_on_commit=False)
            owner, id_map = seed_sqlite(factory, records)
            with patch.object(cache, "SessionLocal", factory):
                for index, card in enumerate(records):
                    random.seed(args.seed + index)
                    generation = await generate(card, index, args.mode, args.seed)
                    random.seed(args.seed + index)
                    hybrid = await evaluate_fallback(factory, id_map["hybrid_policy", card["id"]], owner, generation)
                    random.seed(args.seed + index)
                    offline = await evaluate_fallback(factory, id_map["deck_only", card["id"]], owner,
                                                      {"status": "ollama_unavailable", "choices": []})
                    result = {"id": card["id"], "category": card["category"], "ai_only": generation,
                              "hybrid_policy": hybrid, "deck_only": offline}
                    correct = ai.comparison_key(card["back"])
                    for arm in ARMS:
                        if result[arm]["status"] == "ready":
                            keys = {ai.comparison_key(value) for value in result[arm]["choices"]}
                            assert len(keys) == 3 and "" not in keys and correct not in keys
                    results.append(result)
                    if (index + 1) % 12 == 0:
                        print(f"Evaluated {index + 1}/{len(records)} cards ({args.mode}).", flush=True)
        finally:
            engine.dispose()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "live"), required=True)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).with_name("flashcards.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    records, digest = read_dataset(args.dataset)
    runtime = live_metadata() if args.mode == "live" else {}
    results = asyncio.run(run(records, args))
    report = {
        "mode": args.mode, "seed": args.seed, "model": ai.configured_model(),
        "generation_version": ai.GENERATION_VERSION, "dataset_sha256": digest, **runtime,
        "totals": summarize(results),
        "by_category": {category: summarize([row for row in results if row["category"] == category])
                        for category in sorted({row["category"] for row in results})},
        "cards": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["totals"], indent=2), flush=True)


if __name__ == "__main__":
    main()
