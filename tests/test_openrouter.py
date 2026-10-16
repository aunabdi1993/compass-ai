"""OpenRouterClient against a fake `requests` session (no network)."""

import json

import pytest
import requests

from compass.llm import LLMConnectionError, LLMError, LLMRateLimitError, OpenRouterClient

MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]


class FakeResponse:
    def __init__(self, status=200, body=None, lines=()):
        self.status_code, self._body, self._lines = status, body, lines
        self.text = json.dumps(body) if body is not None else ""
        self.closed = False

    def json(self):
        return self._body

    def iter_lines(self):
        yield from self._lines

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def post(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def sse(*events):
    return [f"data: {json.dumps(e) if e != '[DONE]' else e}".encode() for e in events]


def test_request_matches_openrouter_format():
    session = FakeSession(FakeResponse(body={"choices": [{"message": {"content": "ok"}}]}))
    client = OpenRouterClient("KEY", "https://app.example", session=session)
    client.chat("meta-llama/llama-4-maverick", MESSAGES, 100)
    call = session.calls[0]
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["headers"] == {
        "Authorization": "Bearer KEY",
        "Content-Type": "application/json",
        "X-OpenRouter-Title": "Compass",
        "HTTP-Referer": "https://app.example",
    }
    assert json.loads(call["data"]) == {
        "model": "meta-llama/llama-4-maverick",
        "messages": MESSAGES,
        "max_tokens": 100,
    }
    assert "HTTP-Referer" not in OpenRouterClient("K", session=session)._headers


def test_stream_parses_sse_and_closes():
    lines = [b": OPENROUTER PROCESSING", b""] + sse(
        {"choices": [{"delta": {"content": "Héllo"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        "[DONE]",
    )
    response = FakeResponse(lines=lines)
    session = FakeSession(response)
    chunks = list(OpenRouterClient("K", session=session).stream_chat("m", MESSAGES, 10))
    assert [c["choices"][0]["finish_reason"] for c in chunks] == [None, "stop"]
    assert chunks[0]["choices"][0]["delta"]["content"] == "Héllo"
    assert json.loads(session.calls[0]["data"])["stream"] is True
    assert session.calls[0]["stream"] is True and response.closed


def test_mid_stream_error_chunk_raises():
    response = FakeResponse(lines=sse({"error": {"message": "provider died"}}))
    with pytest.raises(LLMError, match="provider died"):
        list(OpenRouterClient("K", session=FakeSession(response)).stream_chat("m", MESSAGES, 10))
    assert response.closed


def test_http_errors_map_to_typed_exceptions():
    rate = FakeResponse(429, {"error": {"message": "slow down"}})
    with pytest.raises(LLMRateLimitError, match="slow down") as info:
        OpenRouterClient("K", session=FakeSession(rate)).chat("m", MESSAGES, 10)
    assert info.value.status_code == 429
    with pytest.raises(LLMError) as info:
        OpenRouterClient("K", session=FakeSession(FakeResponse(401, {"error": {"message": "bad key"}}))).chat("m", MESSAGES, 10)
    assert info.value.status_code == 401 and not isinstance(info.value, LLMRateLimitError)


def test_network_failure_is_connection_error():
    session = FakeSession(error=requests.ConnectionError("no route"))
    with pytest.raises(LLMConnectionError):
        OpenRouterClient("K", session=session).chat("m", MESSAGES, 10)
