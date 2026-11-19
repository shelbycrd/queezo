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
        sent.append(json.loads(body["messages"][1]["content"])["previous_candidates"])
        return next(responses)

    assert set(run_generator(handler, back="Correct answer")) == {
        "One Choice", "Other Choice", "Third Choice",
    }
    assert sent == [[], ["One Choice"], ["One Choice", "Other Choice"]]


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

    with pytest.raises(DistractorGenerationError, match="not provide enough unique distractors"):
        run_generator(handler)
    assert len(requests) == 3


def test_never_returns_non_json_content():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=b'not JSON')

    with pytest.raises(DistractorGenerationError, match="invalid distractor response"):
        run_generator(handler)
    assert len(requests) == 3


@pytest.mark.parametrize("error_type,message", [
    (httpx.ConnectError, "Could not reach Ollama"),
    (httpx.ReadTimeout, "Ollama timed out"),
])
def test_transport_failures_are_bounded_and_sanitized(error_type, message):
    requests = []

    def handler(request):
        requests.append(request)
        raise error_type("private transport details", request=request)

    with pytest.raises(DistractorGenerationError, match=message) as error:
        run_generator(handler)
    assert "private transport details" not in str(error.value)
    assert len(requests) == 3


def test_attempt_deadline_bounds_a_stalled_response(monkeypatch):
    monkeypatch.setattr(distractors, "ATTEMPT_TIMEOUT", 0.01)
    requests = []

    async def handler(request):
        requests.append(request)
        await asyncio.Event().wait()

    with pytest.raises(DistractorGenerationError, match="Ollama timed out"):
        run_generator(handler)
    assert len(requests) == 3


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
