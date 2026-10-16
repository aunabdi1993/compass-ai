def _chunk(content=None, finish=None):
    return {"choices": [{"delta": {"content": content}, "finish_reason": finish}]}


class FakeLLM:
    """Stand-in for compass.llm.OpenRouterClient."""

    def __init__(self, chunks=("Hello ", "there."), finish_reason="stop", summary="- a\n- b\n- c\n- d\n- e"):
        self.chunks, self.finish_reason, self.summary = chunks, finish_reason, summary
        self.stream_calls, self.chat_calls = [], []

    def stream_chat(self, model, messages, max_tokens):
        self.stream_calls.append({"model": model, "messages": messages, "max_tokens": max_tokens})
        yield {"choices": []}  # providers sometimes send empty-choice chunks
        for text in self.chunks:
            yield _chunk(text)
        yield _chunk(None, self.finish_reason)

    def chat(self, model, messages, max_tokens):
        self.chat_calls.append({"model": model, "messages": messages, "max_tokens": max_tokens})
        return {"choices": [{"message": {"content": self.summary}}]}


class FakeStore:
    """In-memory stand-in for compass.db.Store."""

    def __init__(self, client=None, user_id="u1"):
        self.profile = {}
        self.conversations = {}  # id -> {"summary": str|None, "messages": [...]}
        self.order = []
        self.today = 0

    def get_profile(self):
        return self.profile

    def save_profile(self, **fields):
        self.profile = dict(fields)

    def create_conversation(self):
        cid = f"c{len(self.order) + 1}"
        self.conversations[cid] = {"summary": None, "messages": []}
        self.order.append(cid)
        return cid

    def add_message(self, cid, role, content):
        self.conversations[cid]["messages"].append({"role": role, "content": content})
        if role == "user":
            self.today += 1

    def get_messages(self, cid):
        return self.conversations[cid]["messages"]

    def count_user_messages_today(self):
        return self.today

    def set_summary(self, cid, summary):
        self.conversations[cid]["summary"] = summary

    def recent_summaries(self, limit=5):
        done = [
            {"created_at": "2026-10-01T00:00:00", "summary": self.conversations[c]["summary"]}
            for c in self.order
            if self.conversations[c]["summary"]
        ]
        return done[-limit:]

    def unsummarised_conversations(self, exclude_id=None, limit=5):
        return [c for c in reversed(self.order) if self.conversations[c]["summary"] is None and c != exclude_id][:limit]
