"""LLM calls via OpenRouter (OpenAI-compatible API): streaming coach replies and
end-of-session summaries."""

from collections.abc import Iterator

import openai

from compass.config import BASE_URL
from compass.prompts import SUMMARY_PROMPT

CHAT_MAX_TOKENS = 4096
SUMMARY_MAX_TOKENS = 600


def make_client(api_key: str, site_url: str | None = None) -> openai.OpenAI:
    # Optional attribution headers, shown on OpenRouter's dashboard and rankings.
    headers = {"X-OpenRouter-Title": "Compass"}
    if site_url:
        headers["HTTP-Referer"] = site_url
    return openai.OpenAI(api_key=api_key, base_url=BASE_URL, default_headers=headers)

REFUSAL_NOTICE = (
    "\n\n_I can't help with that one. If you rephrase or tell me more about "
    "what you're trying to achieve, I'll do my best._"
)
TRUNCATED_NOTICE = "\n\n_(My reply was cut off. Say \"continue\" and I'll pick up.)_"


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
    """Iterable of text chunks. After iteration, `stop_reason` is set."""

    def __init__(self, client, model: str, system: str, messages: list[dict]):
        self._client = client
        self._kwargs = dict(
            model=model,
            max_tokens=CHAT_MAX_TOKENS,
            messages=[{"role": "system", "content": system}, *messages],
        )
        self.stop_reason: str | None = None

    def __iter__(self) -> Iterator[str]:
        stream = self._client.chat.completions.create(stream=True, **self._kwargs)
        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.delta and choice.delta.content:
                yield choice.delta.content
            if choice.finish_reason:
                self.stop_reason = choice.finish_reason
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
    response = client.chat.completions.create(
        model=model,
        max_tokens=SUMMARY_MAX_TOKENS,
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": f"<conversation>\n{transcript}\n</conversation>"},
        ],
    )
    return (response.choices[0].message.content or "").strip()
