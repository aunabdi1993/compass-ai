"""LLM calls to OpenRouter's chat completions endpoint, using plain `requests`:
streaming coach replies and end-of-session summaries."""

import json
from collections.abc import Iterator

import requests

from compass.config import BASE_URL
from compass.prompts import SUMMARY_PROMPT

CHAT_MAX_TOKENS = 4096
SUMMARY_MAX_TOKENS = 600
TIMEOUT = (10, 120)  # connect, read (seconds between streamed chunks)

REFUSAL_NOTICE = (
    "\n\n_I can't help with that one. If you rephrase or tell me more about "
    "what you're trying to achieve, I'll do my best._"
)
TRUNCATED_NOTICE = "\n\n_(My reply was cut off. Say \"continue\" and I'll pick up.)_"


class LLMError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class LLMRateLimitError(LLMError):
    pass


class LLMConnectionError(LLMError):
    pass


class OpenRouterClient:
    """Thin wrapper over POST {BASE_URL}/chat/completions."""

    def __init__(self, api_key: str, site_url: str | None = None, session=None):
        self._session = session or requests.Session()
        self._url = f"{BASE_URL}/chat/completions"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": "Compass",  # optional, shown on openrouter.ai
        }
        if site_url:
            self._headers["HTTP-Referer"] = site_url  # optional, shown on openrouter.ai

    def _post(self, payload: dict, stream: bool):
        try:
            response = self._session.post(
                url=self._url,
                headers=self._headers,
                data=json.dumps(payload),
                stream=stream,
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise LLMConnectionError(str(exc)) from exc
        if response.status_code != 200:
            try:
                detail = response.json()["error"]["message"]
            except Exception:
                detail = (response.text or "")[:200]
            response.close()
            error_cls = LLMRateLimitError if response.status_code == 429 else LLMError
            raise error_cls(detail or f"HTTP {response.status_code}", response.status_code)
        return response

    def chat(self, model: str, messages: list[dict], max_tokens: int, temperature: float | None = None) -> dict:
        """Non-streaming request; returns the parsed JSON response."""
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if temperature is not None:
            payload["temperature"] = temperature
        response = self._post(payload, stream=False)
        data = response.json()
        if "error" in data:
            raise LLMError(data["error"].get("message", "unknown error"))
        return data

    def stream_chat(self, model: str, messages: list[dict], max_tokens: int) -> Iterator[dict]:
        """Streaming request; yields each parsed server-sent-event chunk."""
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True}
        response = self._post(payload, stream=True)
        try:
            for raw in response.iter_lines():  # bytes: decode as UTF-8 ourselves
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):  # blanks and ": OPENROUTER PROCESSING" keep-alives
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                chunk = json.loads(body)
                if "error" in chunk:
                    raise LLMError(chunk["error"].get("message", "stream error"))
                yield chunk
        except requests.RequestException as exc:
            raise LLMConnectionError(str(exc)) from exc
        finally:
            response.close()


def to_api_messages(rows: list[dict]) -> list[dict]:
    """Stored rows -> API messages. Merges adjacent same-role turns (e.g. after a
    failed reply) and drops empty ones, so the history is always valid."""
    messages: list[dict] = []
    for row in rows:
        text = (row.get("content") or "").strip()
        if not text:
            continue
        if messages and messages[-1]["role"] == row["role"]:
            messages[-1]["content"] += "\n\n" + text
        else:
            messages.append({"role": row["role"], "content": text})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


class ReplyStream:
    """Iterable of text chunks. After iteration, `stop_reason` holds the finish reason."""

    def __init__(self, client, model: str, system: str, messages: list[dict]):
        self._client = client
        self._model = model
        self._messages = [{"role": "system", "content": system}, *messages]
        self.stop_reason: str | None = None

    def __iter__(self) -> Iterator[str]:
        for chunk in self._client.stream_chat(self._model, self._messages, CHAT_MAX_TOKENS):
            if not chunk.get("choices"):
                continue
            choice = chunk["choices"][0]
            text = (choice.get("delta") or {}).get("content")
            if text:
                yield text
            if choice.get("finish_reason"):
                self.stop_reason = choice["finish_reason"]
        if self.stop_reason == "content_filter":
            yield REFUSAL_NOTICE
        elif self.stop_reason == "length":
            yield TRUNCATED_NOTICE


def stream_reply(client, model: str, system: str, messages: list[dict]) -> ReplyStream:
    return ReplyStream(client, model, system, messages)


def summarise_conversation(client, model: str, rows: list[dict]) -> str:
    """Five-line memory note for a finished conversation ('' if there is nothing to say)."""
    messages = to_api_messages(rows)
    if not any(m["role"] == "assistant" for m in messages):
        return ""
    transcript = "\n\n".join(
        f"{'User' if m['role'] == 'user' else 'Compass'}: {m['content']}" for m in messages
    )
    response = client.chat(
        model,
        [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": f"<conversation>\n{transcript}\n</conversation>"},
        ],
        SUMMARY_MAX_TOKENS,
    )
    return (response["choices"][0]["message"].get("content") or "").strip()
