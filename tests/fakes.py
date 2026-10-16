from types import SimpleNamespace


def _chunk(content=None, finish=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content), finish_reason=finish)]
    )


class FakeCompletions:
    def __init__(self, chunks=("Hello ", "there."), finish_reason="stop", summary="- a\n- b\n- c\n- d\n- e"):
        self.chunks, self.finish_reason, self.summary = chunks, finish_reason, summary
        self.stream_calls, self.create_calls = [], []

    def create(self, stream=False, **kwargs):
        if not stream:
            self.create_calls.append(kwargs)
            message = SimpleNamespace(content=self.summary)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        self.stream_calls.append(kwargs)
        events = [SimpleNamespace(choices=[])]  # providers sometimes send empty-choice chunks
        events += [_chunk(c) for c in self.chunks]
        events.append(_chunk(None, self.finish_reason))
        return iter(events)


class FakeLLM:
    def __init__(self, **kwargs):
        self.completions = FakeCompletions(**kwargs)
        self.chat = SimpleNamespace(completions=self.completions)


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
