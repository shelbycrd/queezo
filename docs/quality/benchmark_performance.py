"""Measure the actual single-worker preparation path with disposable SQLite."""
import argparse
import asyncio
from contextlib import ExitStack
from contextvars import ContextVar
import json
import math
from pathlib import Path
import platform
import random
import resource
import sqlite3
from statistics import mean, median
from tempfile import TemporaryDirectory
from time import perf_counter, process_time, time
from unittest.mock import patch

import httpx
from sqlalchemy import delete, event, select
from sqlalchemy.orm import sessionmaker

from evaluate import SeededTransport, live_metadata
from app.database import init_database, make_engine
from app.models import Deck, Flashcard, FlashcardDistractorCache, FlashcardDistractorSource, MultipleChoiceQuestion, User
from app.services import distractor_cache as cache, distractors as ai, multiple_choice as study

SIZES = (10, 50, 150)
CARD = ContextVar("benchmark_card", default=None)
SQL_GROUP = ContextVar("benchmark_sql_group", default="preparation")
CACHE_BATCH = ContextVar("benchmark_cache_batch", default=None)


def stats(values):
    ordered = sorted(values)
    if not ordered:
        return {"mean": None, "median": None, "p95": None}
    return {"mean": mean(ordered), "median": median(ordered),
            "p95": ordered[math.ceil(0.95 * len(ordered)) - 1]}


def rss_bytes():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("Linux VmRSS is required for resource measurements.")


def seed_deck(factory, size, variant):
    with factory.begin() as db:
        owner = User(email=f"benchmark-{variant}@example.com", password_hash="not-used")
        db.add(owner)
        db.flush()
        deck = Deck(owner_id=owner.id, title=f"Synthetic {size} card deck")
        db.add(deck)
        db.flush()
        cards = [Flashcard(deck_id=deck.id, front=f"What is {i + 101} plus 7? Give an integer.",
                           back=str(i + 108)) for i in range(size)]
        db.add_all(cards)
        db.flush()
        return {"id": deck.id, "owner": owner.id, "cards": [card.id for card in cards]}


class MeasuredTransport(httpx.AsyncBaseTransport):
    def __init__(self, card, mode, seed, inject_outage, scenario_start):
        self.card = card
        self.mode = mode
        self.inject_outage = inject_outage
        self.scenario_start = scenario_start
        self.delegate = SeededTransport(seed) if mode == "live" and not inject_outage else None

    async def handle_async_request(self, request):
        attempts = self.card["requests"]
        trace = {"kind": "injected_outage" if self.inject_outage else self.mode}
        attempts.append(trace)
        start = perf_counter()
        trace["started_s"] = start - self.scenario_start
        try:
            if self.inject_outage:
                raise httpx.ConnectError("Scripted hybrid outage", request=request)
            if self.mode == "live":
                response = await self.delegate.handle_async_request(request)
            else:
                await asyncio.sleep(0.030)
                back = json.loads(json.loads(request.content)["messages"][1]["content"])["correct_answer"]
                candidates = ([back] if self.card["ordinal"] % 10 == 3 and len(attempts) == 1
                              else [str(int(back) + offset) for offset in (1, 2, 3, 4, 5, 6)])
                content = json.dumps({"distractors": candidates})
                response = httpx.Response(200, json={"message": {"content": content}})
            await response.aread()
            trace["status"] = response.status_code
            if response.is_success:
                try:
                    envelope = response.json()
                    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
                        if isinstance(envelope.get(key), int):
                            trace[key + "_ns"] = envelope[key]
                except (ValueError, AttributeError):
                    pass  # Production owns response validation.
            return response
        except httpx.HTTPError as error:
            trace["error"] = type(error).__name__
            raise
        finally:
            trace["elapsed_s"] = perf_counter() - start

    async def aclose(self):
        if self.delegate is not None:
            await self.delegate.aclose()


class MeasuredLock:
    def __init__(self, lock):
        self.lock = lock

    async def __aenter__(self):
        start = perf_counter()
        await self.lock.acquire()
        CARD.get()["model_slot_wait_s"] = perf_counter() - start

    async def __aexit__(self, *_):
        self.lock.release()


async def measure(factory, engine, decks, args, scenario, outage_ids=()):
    started_utc = time()
    start = perf_counter()
    cpu_start = process_time()
    rss = [rss_bytes()]
    card_runs, queries = [], []
    ids = {cid: i for deck in decks for i, cid in enumerate(deck["cards"])}
    pending = getattr(study, "_pending", None)
    prepare_cached = getattr(study, "_prepare_cached", None)
    snapshot = getattr(study, "_snapshot", None)
    save, lookup, generate = study._save_prepared, cache._lookup, ai.generate_distractors
    cache_batches = []

    def sql_begin(conn, cursor, statement, parameters, context, executemany):
        context.benchmark_started = perf_counter()

    def sql_end(conn, cursor, statement, parameters, context, executemany):
        elapsed = perf_counter() - context.benchmark_started
        card = CARD.get()
        queries.append((SQL_GROUP.get(), elapsed))
        if card is not None:
            card["sql_queries"] += 1
            card["sql_s"] += elapsed

    # Resolve pending rows in the same production thread-pool call, before walking them in the event loop.
    def traced_pending(session_id):
        rows = pending(session_id)
        return walk_pending(session_id, rows)

    def traced_snapshot(question, card, choices):
        snapshot(question, card, choices)
        batch = CACHE_BATCH.get()
        if batch is not None:
            batch.append((question.id, card.id))

    def traced_prepare_cached(session_id, attempt):
        batch = []
        cache_token = CACHE_BATCH.set(batch)
        sql_token = SQL_GROUP.set("cache_pass")
        began = perf_counter() - start
        try:
            misses = prepare_cached(session_id, attempt)
        finally:
            CACHE_BATCH.reset(cache_token)
            SQL_GROUP.reset(sql_token)
        finished = perf_counter() - start
        cache_batches.append({"session": session_id, "ready": len(batch), "queued_misses": len(misses),
                              "started_s": began, "finished_s": finished})
        for question_id, card_id in batch:
            card_runs.append({
                "session": session_id, "question": question_id, "card": card_id, "ordinal": ids[card_id],
                "started_s": began, "finished_s": finished, "latency_s": finished - began,
                "cache_hit": True, "batch_snapshot": True, "failure": None,
                "sql_queries": 0, "sql_s": 0.0, "generation_s": 0.0, "requests": [],
            })
        return walk_pending(session_id, misses)

    def walk_pending(session_id, rows):
        for question_id, card_id in rows:
            row = {"session": session_id, "card": card_id, "ordinal": ids[card_id],
                   "started_s": perf_counter() - start, "sql_queries": 0, "sql_s": 0.0,
                   "generation_s": 0.0, "requests": []}
            card_runs.append(row)
            token = CARD.set(row)
            try:
                yield question_id, card_id
            finally:
                CARD.reset(token)

    def traced_save(session_id, attempt, question_id, content, choices, failure):
        save(session_id, attempt, question_id, content, choices, failure)
        row = CARD.get()
        row["finished_s"] = perf_counter() - start
        row["latency_s"] = row["finished_s"] - row["started_s"]
        row["failure"] = failure
        row["question"] = question_id

    def traced_lookup(*values):
        result = lookup(*values)
        CARD.get()["cache_hit"] = result[-1] is not None
        return result

    async def traced_generate(front, back, *, model):
        row = CARD.get()
        t0 = perf_counter()
        transport = MeasuredTransport(row, args.mode, args.seed + row["ordinal"], row["card"] in outage_ids, start)
        try:
            async with httpx.AsyncClient(transport=transport, trust_env=False) as http:
                return await generate(front, back, client=http, model=model)
        finally:
            row["generation_s"] = perf_counter() - t0

    async def sample_rss():
        while True:
            await asyncio.sleep(0.020)
            rss.append(rss_bytes())

    jobs = study.PreparationJobs()
    jobs.model_slot = MeasuredLock(jobs.model_slot)
    sampler = asyncio.create_task(sample_rss())
    event.listen(engine, "before_cursor_execute", sql_begin)
    event.listen(engine, "after_cursor_execute", sql_end)
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(study, "SessionLocal", factory))
            stack.enter_context(patch.object(cache, "SessionLocal", factory))
            stack.enter_context(patch.object(study, "_save_prepared", traced_save))
            stack.enter_context(patch.object(cache, "_lookup", traced_lookup))
            stack.enter_context(patch.object(ai, "generate_distractors", traced_generate))
            if prepare_cached is None:
                stack.enter_context(patch.object(study, "_pending", traced_pending))
            else:
                stack.enter_context(patch.object(study, "_prepare_cached", traced_prepare_cached))
                stack.enter_context(patch.object(study, "_snapshot", traced_snapshot))
            queued = {}
            create_results = []
            token = SQL_GROUP.set("create_session")
            try:
                for deck in decks:
                    began = perf_counter()
                    state, attempt = study.create_session(deck["id"], deck["owner"])
                    create_results.append((state["id"], attempt, perf_counter() - began))
            finally:
                SQL_GROUP.reset(token)
            for session_id, attempt, create_s in create_results:
                queued[session_id] = {"create_s": create_s, "queued_s": perf_counter() - start}
                jobs.start(session_id, attempt)

            async def join(session_id, job):
                await job
                queued[session_id]["finished_s"] = perf_counter() - start

            await asyncio.gather(*(join(sid, job) for sid, job in jobs.current.items()))
    finally:
        event.remove(engine, "before_cursor_execute", sql_begin)
        event.remove(engine, "after_cursor_execute", sql_end)
        sampler.cancel()
        await asyncio.gather(sampler, return_exceptions=True)
    elapsed = perf_counter() - start
    cpu = process_time() - cpu_start
    finished_utc = time()
    rss.append(rss_bytes())
    sessions = []
    with factory() as db:
        fallback_ids = set(db.scalars(select(FlashcardDistractorSource.flashcard_id).where(
            FlashcardDistractorSource.flashcard_id.in_(ids),
        )))
        for session_id, timing in queued.items():
            snapshots = db.scalars(select(MultipleChoiceQuestion).where(
                MultipleChoiceQuestion.session_id == session_id,
            )).all()
            ready_ids = {q.id for q in snapshots if q.correct_option_id is not None}
            times = sorted(row["finished_s"] - timing["queued_s"] for row in card_runs
                           if row.get("question") in ready_ids)
            assert len(times) == len(ready_ids)
            # All benchmark cards must prepare successfully; use the same persisted prefix as the API.
            committed = {row["question"]: row["finished_s"] - timing["queued_s"]
                         for row in card_runs if row.get("question") in ready_ids}
            target = min(getattr(study, "START_QUESTIONS", 5), len(snapshots))
            prefix = sorted(snapshots, key=lambda question: question.position)[:target]
            playable = (max(committed[q.id] for q in prefix)
                        if all(q.id in committed for q in prefix) else None)
            if not hasattr(study, "START_QUESTIONS"):
                playable = timing["finished_s"] - timing["queued_s"] if ready_ids else None
            sessions.append({"id": session_id, "ready": len(ready_ids),
                             "time_to_playable_s": playable,
                             "failed": len(snapshots) - len(ready_ids),
                             "time_to_first_s": times[0] if times else None,
                             "time_to_five_s": times[4] if len(times) >= 5 else None,
                             "preparation_s": timing["finished_s"] - timing["queued_s"], **timing})
    requests = [r for row in card_runs for r in row["requests"]]
    count = peak = 0
    boundaries = [(point, delta) for req in requests
                  for point, delta in ((req["started_s"], 1), (req["started_s"] + req["elapsed_s"], -1))]
    for _, delta in sorted(boundaries):
        count += delta
        peak = max(peak, count)
    hits = sum(row.get("cache_hit") is True for row in card_runs)
    misses = sum(row.get("cache_hit") is False for row in card_runs)
    sql = {}
    for group, seconds in queries:
        entry = sql.setdefault(group, {"queries": 0, "cursor_s": 0.0})
        entry["queries"] += 1
        entry["cursor_s"] += seconds
    return {
        "scenario": scenario, "size": len(decks[0]["cards"]), "sessions": sessions,
        "started_utc_epoch": started_utc, "finished_utc_epoch": finished_utc, "wall_s": elapsed,
        "per_card_latency_s": stats([row["latency_s"] for row in card_runs if "latency_s" in row]),
        "per_card_slot_wait_s": stats([row["model_slot_wait_s"] for row in card_runs if "model_slot_wait_s" in row]),
        "cache": {"hits": hits, "misses": misses, "hit_rate": hits / (hits + misses) if hits + misses else None},
        "sql": sql, "cache_passes": cache_batches, "python_cpu_s": cpu, "python_avg_cpu_pct_one_core": 100 * cpu / elapsed,
        "python_peak_rss_bytes": max(rss), "python_process_high_water_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "peak_request_concurrency": peak,
        "generated_cards_using_deck_fallback": sum(row.get("cache_hit") is False and row["card"] in fallback_ids
                                                   for row in card_runs),
        "requests": len(requests), "live_ollama_requests": sum(r["kind"] == "live" for r in requests),
        "injected_outages": sum(r["kind"] == "injected_outage" for r in requests),
        "retries": sum(max(0, len(row["requests"]) - 1) for row in card_runs),
        "generation_wall_s": sum(row["generation_s"] for row in card_runs),
        "live_ollama_http_wall_s": sum(r["elapsed_s"] for r in requests if r["kind"] == "live"),
        "ollama_reported_total_s": sum(r.get("total_duration_ns", 0) for r in requests) / 1e9,
        "cards": card_runs,
    }


async def suite(args, engine, factory, report):
    def save(result):
        report["scenarios"].append(result)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"{result['scenario']} {result['size']}: {result['wall_s']:.3f}s "
              f"({sum(s['ready'] for s in result['sessions'])} ready)", flush=True)

    for size in args.sizes:
        deck = seed_deck(factory, size, size)
        random.seed(args.seed)
        cold = await measure(factory, engine, [deck], args, "cold")
        save(cold)
        if args.cold_only:
            continue
        if cold["sessions"][0]["ready"] != size:
            raise RuntimeError("Cold run did not fill the cache. Recorded partial results; warm scenario skipped.")
        random.seed(args.seed)
        warm = await measure(factory, engine, [deck], args, "warm")
        save(warm)
        assert warm["cache"]["hits"] == size and warm["requests"] == 0
        # Remove only odd zero-based positions from the synthetic database. Force an outage
        # on positions ending in 1 so this scenario always exercises deck fallback.
        with factory.begin() as db:
            db.execute(delete(FlashcardDistractorCache).where(
                FlashcardDistractorCache.flashcard_id.in_(deck["cards"][1::2]),
            ))
        random.seed(args.seed)
        hybrid = await measure(factory, engine, [deck], args, "hybrid", set(deck["cards"][1::10]))
        save(hybrid)
        assert hybrid["cache"]["hits"] == size // 2 and hybrid["cache"]["misses"] == size // 2

    if args.cold_only:
        return
    decks = [seed_deck(factory, 10, f"concurrent-{i}") for i in range(2)]
    random.seed(args.seed)
    save(await measure(factory, engine, decks, args, "two_cold_sessions"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("live", "mock"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sizes", type=int, choices=SIZES, nargs="+", default=SIZES)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cold-only", action="store_true")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "mode": args.mode, "seed": args.seed, "cold_only": args.cold_only, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "container_kernel": platform.release(), "model": ai.configured_model(),
        "generation_version": ai.GENERATION_VERSION, "attempt_timeout_s": ai.ATTEMPT_TIMEOUT,
        "max_attempts": ai.MAX_ATTEMPTS, "preparation_timeout_s": study.PREPARATION_TIMEOUT,
        "mock_delay_ms": 30 if args.mode == "mock" else None, "scenarios": [],
        **(live_metadata() if args.mode == "live" else {}),
    }
    with TemporaryDirectory(prefix="queezo-perf-") as directory:
        engine = make_engine(f"sqlite:///{(Path(directory) / 'perf.db').as_posix()}")
        try:
            init_database(engine)
            with engine.connect() as connection:
                report["journal_mode"] = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
            asyncio.run(suite(args, engine, sessionmaker(bind=engine, expire_on_commit=False), report))
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
