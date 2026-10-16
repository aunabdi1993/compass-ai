"""Supabase data access. One Store per signed-in user; Row Level Security does the
real isolation, the user_id filters here are belt and braces."""

from datetime import datetime, timezone

PROFILE_FIELDS = ("role", "industry", "goals", "cv_text")


class Store:
    def __init__(self, client, user_id: str):
        self._client = client
        self._user_id = user_id

    def _table(self, name: str):
        return self._client.table(name)

    # profile ---------------------------------------------------------------
    def get_profile(self) -> dict:
        res = self._table("profiles").select("*").eq("user_id", self._user_id).limit(1).execute()
        return res.data[0] if res.data else {}

    def save_profile(self, **fields) -> None:
        row = {key: fields.get(key, "") for key in PROFILE_FIELDS}
        row["user_id"] = self._user_id
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._table("profiles").upsert(row).execute()

    # conversations ---------------------------------------------------------
    def create_conversation(self) -> str:
        res = self._table("conversations").insert({"user_id": self._user_id}).execute()
        return res.data[0]["id"]

    def add_message(self, conversation_id: str, role: str, content: str) -> int:
        res = self._table("messages").insert(
            {
                "conversation_id": conversation_id,
                "user_id": self._user_id,
                "role": role,
                "content": content,
            }
        ).execute()
        return res.data[0]["id"]

    def set_feedback(self, message_id: int, value: int | None) -> None:
        """Thumbs up (1), thumbs down (-1), or cleared (None), saved on the message."""
        self._table("messages").update(
            {
                "feedback": value,
                "feedback_at": datetime.now(timezone.utc).isoformat() if value else None,
            }
        ).eq("id", message_id).eq("user_id", self._user_id).execute()

    def get_messages(self, conversation_id: str) -> list[dict]:
        res = (
            self._table("messages")
            .select("id, role, content, created_at, feedback")
            .eq("conversation_id", conversation_id)
            .order("id")
            .execute()
        )
        return res.data

    def count_user_messages_today(self) -> int:
        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        res = (
            self._table("messages")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .eq("role", "user")
            .gte("created_at", midnight.isoformat())
            .execute()
        )
        return res.count or 0

    # memory ----------------------------------------------------------------
    def set_summary(self, conversation_id: str, summary: str) -> None:
        self._table("conversations").update({"summary": summary}).eq("id", conversation_id).execute()

    def recent_summaries(self, limit: int = 5) -> list[dict]:
        """Newest `limit` summaries, returned oldest-first."""
        res = (
            self._table("conversations")
            .select("created_at, summary")
            .eq("user_id", self._user_id)
            .not_.is_("summary", "null")
            .neq("summary", "")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(reversed(res.data))

    def unsummarised_conversations(self, exclude_id: str | None = None, limit: int = 5) -> list[str]:
        """Ids of finished-but-never-summarised conversations (e.g. the tab was just closed)."""
        query = (
            self._table("conversations")
            .select("id")
            .eq("user_id", self._user_id)
            .is_("summary", "null")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if exclude_id:
            query = query.neq("id", exclude_id)
        return [row["id"] for row in query.execute().data]

    # consent ---------------------------------------------------------------
    def get_consent(self) -> dict:
        res = self._table("consents").select("*").eq("user_id", self._user_id).limit(1).execute()
        return res.data[0] if res.data else {}

    def save_consent(self, version: str, training_opt_in: bool) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table("consents").upsert(
            {
                "user_id": self._user_id,
                "version": version,
                "accepted_at": now,
                "training_opt_in": training_opt_in,
                "updated_at": now,
            }
        ).execute()

    def set_training_opt_in(self, opted_in: bool) -> None:
        self._table("consents").update(
            {"training_opt_in": opted_in, "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("user_id", self._user_id).execute()

    # documents -------------------------------------------------------------
    def list_documents(self) -> list[dict]:
        res = (
            self._table("documents")
            .select("id, name, content, char_count, truncated, enabled, created_at")
            .eq("user_id", self._user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return res.data

    def add_document(self, name: str, content: str, truncated: bool) -> None:
        self._table("documents").insert(
            {
                "user_id": self._user_id,
                "name": name,
                "content": content,
                "char_count": len(content),
                "truncated": truncated,
            }
        ).execute()

    def set_document_enabled(self, document_id: str, enabled: bool) -> None:
        self._table("documents").update({"enabled": enabled}).eq("id", document_id).eq(
            "user_id", self._user_id
        ).execute()

    def delete_document(self, document_id: str) -> None:
        self._table("documents").delete().eq("id", document_id).eq("user_id", self._user_id).execute()

    # privacy ---------------------------------------------------------------
    def delete_my_data(self) -> None:
        """Remove chats, documents, profile and consent in one database call."""
        self._client.rpc("delete_my_data").execute()

    # conversation history ----------------------------------------------------
    def get_conversation(self, conversation_id: str) -> dict | None:
        res = (
            self._table("conversations")
            .select("id, created_at, summary")
            .eq("id", conversation_id)
            .eq("user_id", self._user_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def clear_summary(self, conversation_id: str) -> None:
        """A conversation that gets new messages needs a fresh summary later."""
        self._table("conversations").update({"summary": None}).eq("id", conversation_id).eq(
            "user_id", self._user_id
        ).execute()

    def list_conversations(self, limit: int = 30) -> list[dict]:
        """Newest first, each with a title taken from its first user message."""
        convs = (
            self._table("conversations")
            .select("id, created_at, summary")
            .eq("user_id", self._user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        if not convs:
            return []
        firsts = (
            self._table("messages")
            .select("conversation_id, content")
            .in_("conversation_id", [c["id"] for c in convs])
            .eq("role", "user")
            .order("id")
            .execute()
            .data
        )
        titles: dict[str, str] = {}
        for row in firsts:
            titles.setdefault(row["conversation_id"], row["content"])
        return [
            {
                "id": c["id"],
                "created_at": c["created_at"],
                "title": " ".join(titles.get(c["id"], "New conversation").split())[:70],
                "ended": bool(c.get("summary")),
            }
            for c in convs
        ]
