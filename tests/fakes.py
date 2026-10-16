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

    def chat(self, model, messages, max_tokens, temperature=None):
        self.chat_calls.append({"model": model, "messages": messages, "max_tokens": max_tokens})
        return {"choices": [{"message": {"content": self.summary}}]}


class FakeStore:
    """In-memory stand-in for compass.db.Store."""

    def __init__(self, client=None, user_id="u1", consented=True):
        from compass.consent import CONSENT_VERSION

        self.profile = {}
        self.conversations = {}  # id -> {"summary": str|None, "messages": [...]}
        self.order = []
        self.today = 0
        self.next_message_id = 1
        self.documents = []
        self.consent = {"version": CONSENT_VERSION, "training_opt_in": False} if consented else {}
        self.deleted = False

    # profile
    def get_profile(self):
        return self.profile

    def save_profile(self, **fields):
        self.profile = dict(fields)

    # conversations
    def create_conversation(self):
        cid = f"c{len(self.order) + 1}"
        self.conversations[cid] = {"summary": None, "messages": []}
        self.order.append(cid)
        return cid

    def add_message(self, cid, role, content):
        message = {"id": self.next_message_id, "role": role, "content": content, "feedback": None}
        self.next_message_id += 1
        self.conversations[cid]["messages"].append(message)
        if role == "user":
            self.today += 1
        return message["id"]

    def set_feedback(self, message_id, value):
        for conv in self.conversations.values():
            for message in conv["messages"]:
                if message["id"] == message_id:
                    message["feedback"] = value

    def get_messages(self, cid):
        return self.conversations[cid]["messages"]

    def get_conversation(self, cid):
        conv = self.conversations.get(cid)
        return {"id": cid, "summary": conv["summary"]} if conv else None

    def clear_summary(self, cid):
        self.conversations[cid]["summary"] = None

    def list_conversations(self, limit=30):
        out = []
        for cid in reversed(self.order):
            first = next((m["content"] for m in self.conversations[cid]["messages"] if m["role"] == "user"), "New conversation")
            out.append({"id": cid, "created_at": "2026-10-01T00:00:00", "title": first[:70],
                        "ended": bool(self.conversations[cid]["summary"])})
        return out[:limit]

    def count_user_messages_today(self):
        return self.today

    # memory
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

    # consent
    def get_consent(self):
        return self.consent

    def save_consent(self, version, training_opt_in):
        self.consent = {"version": version, "training_opt_in": training_opt_in}

    def set_training_opt_in(self, opted_in):
        self.consent["training_opt_in"] = opted_in

    # documents
    def list_documents(self):
        return sorted(self.documents, key=lambda d: d["created_at"], reverse=True)

    def add_document(self, name, content, truncated):
        n = len(self.documents) + 1
        self.documents.append(
            {"id": f"d{n}", "name": name, "content": content, "char_count": len(content),
             "truncated": truncated, "enabled": True, "created_at": f"2026-10-{n:02d}"}
        )

    def set_document_enabled(self, document_id, enabled):
        for doc in self.documents:
            if doc["id"] == document_id:
                doc["enabled"] = enabled

    def delete_document(self, document_id):
        self.documents = [d for d in self.documents if d["id"] != document_id]

    # privacy
    def delete_my_data(self):
        self.deleted = True
        self.profile, self.conversations, self.order = {}, {}, []
        self.documents, self.consent = [], {}
