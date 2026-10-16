"""Session memory: summarise finished conversations, load them into the next prompt."""

from compass.llm import summarise_conversation

SUMMARIES_IN_PROMPT = 5


def end_conversation(store, client, model: str, conversation_id: str) -> bool:
    """Summarise a conversation and store the note. Returns True if one was saved."""
    summary = summarise_conversation(client, model, store.get_messages(conversation_id))
    if summary:
        store.set_summary(conversation_id, summary)
    return bool(summary)


def catch_up(store, client, model: str, current_id: str | None = None) -> int:
    """Summarise earlier conversations that ended without an explicit 'end session'
    (the user closed the tab). Conversations with nothing to summarise are skipped
    and retried next time, which is cheap because they are empty or one-sided."""
    done = 0
    for conversation_id in store.unsummarised_conversations(exclude_id=current_id):
        if end_conversation(store, client, model, conversation_id):
            done += 1
    return done
