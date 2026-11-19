import asyncio
import json

import httpx
import pytest

from app.services import distractors
from app.services.distractors import DistractorGenerationError, generate_distractors


def reply(candidates):
    return httpx.Response(200, json={
        "message": {"content": json.dumps({"distractors": candidates})},
    })


def run_generator(handler, front="What is the capital of Japan?", back="Tokyo"):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await generate_distractors(front, back, client=client)

    return asyncio.run(run())


def test_request_uses_chat_json_mode_and_samples_three_valid_candidates(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    sample_calls = []

    def sample(candidates, count):
        sample_calls.append((candidates.copy(), count))
        return candidates[-count:]

    monkeypatch.setattr(distractors.random, "sample", sample)

    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "http://host.docker.internal:11434/api/chat"
        body = json.loads(request.content)
        assert body["model"] == "qwen3:1.7b"
        assert body["format"] == "json"
        assert body["think"] is False and body["stream"] is False
        assert "six" in body["messages"][0]["content"]
        assert json.loads(body["messages"][1]["content"]) == {
            "question": "What is the capital of Japan?",
            "correct_answer": "Tokyo",
            "previous_candidates": [],
        }
        assert request.extensions["timeout"]["connect"] == 5.0
        assert request.extensions["timeout"]["read"] == 60.0
        return reply(["Kyoto", "Osaka", "Nara", "Nagoya", "Sapporo", "Kobe"])

    assert run_generator(handler) == ["Nagoya", "Sapporo", "Kobe"]
    assert sample_calls == [(["Kyoto", "Osaka", "Nara", "Nagoya", "Sapporo", "Kobe"], 3)]


def test_filters_matches_duplicates_and_malformed_values_across_retries(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.local:12345/")
    monkeypatch.setenv("OLLAMA_MODEL", "local-model:test")
    responses = iter([
        reply([" \tCORRECT 　 ANSWER\n", "  One Choice  ", "one\tchoice", None, {}, "  "]),
        reply(["ONE CHOICE", "Other Choice", 7, False, [], "correct answer"]),
        reply(["\n OTHER   choice ", "Third Choice", "correct answer"]),
    ])
    sent = []

    def handler(request):
        assert str(request.url) == "http://ollama.local:12345/api/chat"
        body = json.loads(request.content)
        assert body["model"] == "local-model:test"
        sent.append(json.loads(body["messages"][1]["content"]))
        return next(responses)

    assert set(run_generator(handler, back="Correct answer")) == {
        "One Choice", "Other Choice", "Third Choice",
    }
    assert [card["previous_candidates"] for card in sent] == [[], ["One Choice"], ["One Choice", "Other Choice"]]
    assert [card["remaining"] for card in sent[1:]] == [2, 1]
    assert sent[1]["rejection_counts"] == {"correct_answer": 1, "duplicate": 1, "blank_or_nontext": 3}
    assert {distractors.comparison_key(choice) for choice in sent[1]["rejected_candidates"]} == {
        "correct answer", "one choice",
    }


@pytest.mark.parametrize("bad_response", [
    {"message": {"content": ' ```json\n{"distractors":["Kyoto"]}\n``` '}},
    {"message": {"content": '{"distractors": ["Kyoto", NaN]}'}},
    {"message": {"content": '{"distractors": "Kyoto"}'}},
    {"message": {"content": '["Kyoto"]'}},
    {"message": {"content": '{"other": ["Kyoto"]}'}},
    {"message": {"content": None}},
    {"message": []},
    None,
])
def test_retries_invalid_json_or_response_structure(bad_response):
    responses = iter([
        reply(["Kyoto"]),
        httpx.Response(200, json=bad_response),
        reply(["Osaka", "Nara"]),
    ])
    assert set(run_generator(lambda _: next(responses))) == {"Kyoto", "Osaka", "Nara"}


def test_fails_after_three_attempts_without_enough_choices():
    requests = []

    def handler(request):
        requests.append(request)
        return reply(["Tokyo", "tOkYo", "Kyoto", "Kyoto", " ", None])

    with pytest.raises(DistractorGenerationError, match="not provide enough unique distractors") as error:
        run_generator(handler)
    assert error.value.candidates == ("Kyoto",)
    assert len(requests) == 3


@pytest.mark.parametrize("front,back,alternatives", [
    ("awgaw", "asdaw", ["asdax", "asdaq", "asdas"]),
    ("awgaa", "awdawd", ["awdaxx", "awdawx", "awdawp"]),
    ("gasdfg", "awdawd", ["awdaxx", "awdawx", "awdawp"]),
    ("tyjyukyu", "khl", ["khk", "kfh", "kll"]),
])
def test_keyboard_pattern_cards_adapt_and_keep_valid_choices(front, back, alternatives):
    sent = []

    def handler(request):
        body = json.loads(request.content)
        system, user = body["messages"]
        assert body["format"] == "json" and body["think"] is False
        card = json.loads(user["content"])
        sent.append((system["content"], card))
        if len(sent) == 1:
            assert "six plausible but incorrect" in system["content"]
            return reply([back.upper(), "", "A wholly different format", None])
        assert "Treat both sides as literal strings" in system["content"]
        assert "rejected_candidates" in system["content"]
        if len(sent) == 2:
            assert card["previous_candidates"] == []
            assert card["remaining"] == 3
            assert "A wholly different format" in card["rejected_candidates"]
            return reply([alternatives[0], back, "Wrong Shape"])
        assert card["previous_candidates"] == [alternatives[0]]
        assert card["remaining"] == 2
        assert card["rejection_counts"]["format_mismatch"] == 2
        return reply([alternatives[0].upper(), alternatives[1], alternatives[2]])

    assert set(run_generator(handler, front=front, back=back)) == set(alternatives)
    assert len(sent) == 3
    assert "fill 2 remaining slots" in sent[2][0]


@pytest.mark.parametrize("front,back", [
    ("What is the capital of Japan?", "Tokyo"),
    ("chaperonin", "groel"),
    ("murmur", "sound"),
    ("What is the name of this C++ identifier?", "std::move"),
    ("QWERTY", "DNA"),
    ("gasdfg", "quark"),
    ("keyboard", "qwerty"),
    ("manager", "asdf"),
])
def test_failed_conceptual_attempts_do_not_trigger_literal_mode(front, back):
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body["messages"][0]["content"])
        return reply([back])

    with pytest.raises(DistractorGenerationError) as error:
        run_generator(handler, front=front, back=back)
    assert error.value.reason == "insufficient_distractors"
    assert len(sent) == 3 and len(set(sent)) == 3
    assert all("related to the topic" in prompt and "literal strings" not in prompt for prompt in sent)


def test_lone_unicode_surrogate_is_rejected_without_losing_valid_candidates():
    requests = []
    responses = iter([reply(["\ud800", "Kyoto", "🌏"]), reply(["Osaka"])])

    def handler(request):
        requests.append(json.loads(request.content))
        return next(responses)

    assert set(run_generator(handler)) == {"Kyoto", "🌏", "Osaka"}
    assert len(requests) == 2
    retry = json.loads(requests[1]["messages"][1]["content"])
    assert retry["previous_candidates"] == ["Kyoto", "🌏"]
    assert retry["rejection_counts"] == {"invalid_unicode": 1}
    assert retry["rejected_candidates"] == []


def test_never_returns_non_json_content():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=b'not JSON')

    with pytest.raises(DistractorGenerationError, match="invalid distractor response") as error:
        run_generator(handler)
    assert error.value.reason == "invalid_ai_response"
    assert len(requests) == 3


@pytest.mark.parametrize("error_type,message,attempts,reason", [
    (httpx.ConnectError, "Could not reach Ollama", 1, "ollama_unavailable"),
    (httpx.ConnectTimeout, "Could not reach Ollama", 1, "ollama_unavailable"),
    (httpx.ReadTimeout, "Ollama timed out", 3, "generation_timeout"),
])
def test_transport_failures_are_bounded_and_sanitized(error_type, message, attempts, reason):
    requests = []

    def handler(request):
        requests.append(request)
        raise error_type("private transport details", request=request)

    with pytest.raises(DistractorGenerationError, match=message) as error:
        run_generator(handler)
    assert "private transport details" not in str(error.value)
    assert error.value.reason == reason
    assert len(requests) == attempts


def test_attempt_deadline_bounds_a_stalled_response(monkeypatch):
    monkeypatch.setattr(distractors, "ATTEMPT_TIMEOUT", 0.01)
    requests = []

    async def handler(request):
        requests.append(request)
        await asyncio.Event().wait()

    with pytest.raises(DistractorGenerationError, match="Ollama timed out"):
        run_generator(handler)
    assert len(requests) == 3


def test_connection_failure_preserves_previously_accepted_candidates():
    responses = iter([reply(["Kyoto", "Osaka"]), None])
    requests = []

    def handler(request):
        requests.append(request)
        response = next(responses)
        if response is None:
            raise httpx.ConnectError("Unavailable", request=request)
        return response

    with pytest.raises(DistractorGenerationError, match="Could not reach Ollama") as error:
        run_generator(handler)
    assert error.value.candidates == ("Kyoto", "Osaka")
    assert len(requests) == 2


def test_retries_transient_http_failure():
    responses = iter([httpx.Response(503), reply(["Kyoto", "Osaka", "Nara"])])
    assert set(run_generator(lambda _: next(responses))) == {"Kyoto", "Osaka", "Nara"}


def test_reports_missing_model_without_retrying_or_leaking_response_body():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(404, json={"error": "private model details"})

    with pytest.raises(DistractorGenerationError, match=r"HTTP 404") as error:
        run_generator(handler)
    assert "private model details" not in str(error.value)
    assert len(requests) == 1


@pytest.mark.parametrize("front,back", [("", "Tokyo"), ("Capital of Japan?", " \t")])
def test_rejects_blank_card_text_without_contacting_ollama(front, back):
    with pytest.raises(ValueError, match="nonblank front and back"):
        run_generator(lambda _: pytest.fail("Unexpected Ollama request"), front, back)


def test_rejects_invalid_configuration_without_contacting_ollama(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "not-a-url")
    with pytest.raises(DistractorGenerationError, match="OLLAMA_BASE_URL"):
        run_generator(lambda _: pytest.fail("Unexpected Ollama request"))
