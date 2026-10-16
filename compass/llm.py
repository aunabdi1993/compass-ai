"""Anthropic calls: streaming coach replies and end-of-session summaries."""

from collections.abc import Iterator

import anthropic

from compass.prompts import SUMMARY_PROMPT

CHAT_MAX_TOKENS = 16000
SUMMARY_MAX_TOKENS = 4000

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
            system=system,
            messages=messages,
            output_config={"effort": "medium"},
        )
        self.stop_reason: str | None = None

    def __iter__(self) -> Iterator[str]:
        with self._client.messages.stream(**self._kwargs) as stream:
            yield from stream.text_stream
            self.stop_reason = stream.get_final_message().stop_reason
        if self.stop_reason == "refusal":
            yield REFUSAL_NOTICE
        elif self.stop_reason == "max_tokens":
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
    response = client.messages.create(
        model=model,
        max_tokens=SUMMARY_MAX_TOKENS,
        system=SUMMARY_PROMPT,
        messages=[{"role": "user", "content": f"<conversation>\n{transcript}\n</conversation>"}],
        output_config={"effort": "low"},
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text.strip()
