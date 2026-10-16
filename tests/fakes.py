from types import SimpleNamespace


class FakeStream:
    def __init__(self, chunks, stop_reason="end_turn"):
        self.text_stream = iter(chunks)
        self._stop = stop_reason

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self._stop)


class FakeMessages:
    def __init__(self, chunks=("Hello ", "there."), stop_reason="end_turn", summary="- a\n- b\n- c\n- d\n- e"):
        self.chunks, self.stop_reason, self.summary = chunks, stop_reason, summary
        self.stream_calls, self.create_calls = [], []

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        return FakeStream(self.chunks, self.stop_reason)

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        block = SimpleNamespace(type="text", text=self.summary)
        return SimpleNamespace(content=[SimpleNamespace(type="thinking"), block])


class FakeLLM:
    def __init__(self, **kwargs):
        self.messages = FakeMessages(**kwargs)


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
