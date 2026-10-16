"""Supabase data access. One Store per signed-in user; Row Level Security does the
real isolation, the user_id filters here are belt and braces."""

from datetime import datetime, timezone

PROFILE_FIELDS = ("role", "industry", "goals", "cv_text")


class Store:
    def __init__(self, client, user_id: str):
        self._client = client
        self._user_id = user_id

    def _table(self, name: str):
        # get_session() refreshes the access token if it has expired.
        self._client.auth.get_session()
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

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        self._table("messages").insert(
            {
                "conversation_id": conversation_id,
                "user_id": self._user_id,
                "role": role,
                "content": content,
            }
        ).execute()

    def get_messages(self, conversation_id: str) -> list[dict]:
        res = (
            self._table("messages")
            .select("role, content, created_at")
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
