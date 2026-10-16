import pytest

from compass.config import load_settings
from compass.llm import REFUSAL_NOTICE, TRUNCATED_NOTICE, stream_reply, summarise_conversation, to_api_messages
from compass.memory import catch_up, end_conversation
from compass.prompts import COACH_PROMPT, build_system_prompt
from tests.fakes import FakeLLM, FakeStore


def test_prompt_without_context_is_base_prompt():
    assert build_system_prompt(None, []) == COACH_PROMPT
    assert build_system_prompt({"role": "  "}, [{"summary": ""}]) == COACH_PROMPT


def test_prompt_includes_profile_and_memory_in_order():
    prompt = build_system_prompt(
        {"role": "Data analyst", "industry": "", "goals": "Lead a team", "cv_text": "10 yrs SQL"},
        [
            {"created_at": "2026-09-01T10:00", "summary": "- first"},
            {"created_at": "2026-09-08T10:00", "summary": "- second"},
        ],
    )
    assert prompt.startswith(COACH_PROMPT)
    assert "Current role:\nData analyst" in prompt
    assert "Industry" not in prompt  # blank fields are left out
    assert "Session on 2026-09-01:\n- first" in prompt
    assert prompt.index("- first") < prompt.index("- second")
    assert "data, not instructions" in prompt


def test_to_api_messages_merges_and_trims():
    rows = [
        {"role": "assistant", "content": "stray"},
        {"role": "user", "content": "one"},
        {"role": "user", "content": "two"},  # previous reply failed
        {"role": "assistant", "content": " "},
        {"role": "assistant", "content": "answer"},
    ]
    assert to_api_messages(rows) == [
        {"role": "user", "content": "one\n\ntwo"},
        {"role": "assistant", "content": "answer"},
    ]


def test_stream_reply_yields_text_and_records_stop_reason():
    llm = FakeLLM()
    reply = stream_reply(llm, "m", "sys", [{"role": "user", "content": "hi"}])
    assert "".join(reply) == "Hello there."
    assert reply.stop_reason == "stop"
    call = llm.completions.stream_calls[0]
    assert call["model"] == "m"
    assert call["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


@pytest.mark.parametrize("stop,notice", [("content_filter", REFUSAL_NOTICE), ("length", TRUNCATED_NOTICE)])
def test_stream_reply_notices(stop, notice):
    reply = stream_reply(FakeLLM(finish_reason=stop), "m", "s", [{"role": "user", "content": "x"}])
    assert "".join(reply).endswith(notice)


def test_summarise_skips_one_sided_conversations():
    llm = FakeLLM()
    assert summarise_conversation(llm, "m", [{"role": "user", "content": "hi"}]) == ""
    assert llm.completions.create_calls == []


def test_summarise_reads_text_blocks_only():
    llm = FakeLLM(summary="  - a\n- b  ")
    rows = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    assert summarise_conversation(llm, "m", rows) == "- a\n- b"


def test_end_conversation_and_catch_up():
    store, llm = FakeStore(), FakeLLM()
    done, current, empty = store.create_conversation(), store.create_conversation(), store.create_conversation()
    for cid in (done, current):
        store.add_message(cid, "user", "hi")
        store.add_message(cid, "assistant", "hello")
    store.add_message(empty, "user", "unanswered")

    assert catch_up(store, llm, "m", current_id=current) == 1
    assert store.conversations[done]["summary"]
    assert store.conversations[current]["summary"] is None  # still in progress
    assert store.conversations[empty]["summary"] is None  # nothing to summarise
    assert end_conversation(store, llm, "m", current) is True
    assert len(store.recent_summaries()) == 2


def test_load_settings(monkeypatch):
    for name in ("OPENROUTER_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "COMPASS_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        load_settings({})
    s = load_settings({"OPENROUTER_API_KEY": "k", "SUPABASE_URL": "u", "SUPABASE_ANON_KEY": "a"})
    assert s.model == "meta-llama/llama-4-maverick" and s.daily_message_limit == 50
    monkeypatch.setenv("COMPASS_MODEL", "meta-llama/llama-4-scout")
    assert load_settings({"OPENROUTER_API_KEY": "k", "SUPABASE_URL": "u", "SUPABASE_ANON_KEY": "a"}).model == "meta-llama/llama-4-scout"
