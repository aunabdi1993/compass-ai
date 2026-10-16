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
    call = llm.stream_calls[0]
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
    assert llm.chat_calls == []


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


BASE = {"OPENROUTER_API_KEY": "k", "SUPABASE_URL": "https://abc.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_a"}


def test_load_settings_defaults_and_overrides():
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        load_settings({})
    s = load_settings(BASE)
    assert s.model == "meta-llama/llama-4-maverick" and s.daily_message_limit == 50
    assert s.jwt_issuer == "https://abc.supabase.co/auth/v1"
    assert s.jwks_endpoint == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"
    custom = load_settings({**BASE, "COMPASS_MODEL": "meta-llama/llama-4-scout", "SUPABASE_JWKS_URL": "https://x/jwks", "MAX_USER_MESSAGES_PER_DAY": "7"})
    assert (custom.model, custom.jwks_endpoint, custom.daily_message_limit) == ("meta-llama/llama-4-scout", "https://x/jwks", 7)


def test_legacy_anon_key_name_still_works():
    env = {k: v for k, v in BASE.items() if k != "SUPABASE_PUBLISHABLE_KEY"} | {"SUPABASE_ANON_KEY": "anon"}
    assert load_settings(env).supabase_key == "anon"


def test_secret_keys_are_rejected():
    import base64, json

    def jwt_with(role):
        body = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
        return f"h.{body}.s"

    for bad in ("sb_secret_abc", jwt_with("service_role")):
        with pytest.raises(RuntimeError, match="secret"):
            load_settings({**BASE, "SUPABASE_PUBLISHABLE_KEY": bad})
    assert load_settings({**BASE, "SUPABASE_PUBLISHABLE_KEY": jwt_with("anon")}).supabase_key


def test_dotenv_file_is_loaded_without_overriding_real_variables(tmp_path, monkeypatch):
    from compass.config import load_dotenv_file

    (tmp_path / ".env").write_text("# comment\nFOO_TEST=from-file\nBAR_TEST=\"quoted value\"\nKEPT_TEST=file\n")
    monkeypatch.setenv("KEPT_TEST", "real")
    monkeypatch.delenv("FOO_TEST", raising=False)
    monkeypatch.delenv("BAR_TEST", raising=False)
    load_dotenv_file(tmp_path / ".env")
    import os

    assert (os.environ["FOO_TEST"], os.environ["BAR_TEST"], os.environ["KEPT_TEST"]) == ("from-file", "quoted value", "real")
    load_dotenv_file(tmp_path / "missing.env")  # no error


def test_missing_config_error_points_to_dot_env_not_the_example_file():
    with pytest.raises(RuntimeError) as info:
        load_settings({})
    message = str(info.value)
    assert ".env" in message and "copy .env.example to .env" in message and "not read" in message
    assert all(name in message for name in ("OPENROUTER_API_KEY", "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"))


def test_dotenv_values_with_inline_spaces_and_quotes(tmp_path, monkeypatch):
    import os

    from compass.config import load_dotenv_file

    (tmp_path / ".env").write_text("SPACED_TEST = value with spaces \nSINGLE_TEST='single'\n")
    monkeypatch.delenv("SPACED_TEST", raising=False)
    monkeypatch.delenv("SINGLE_TEST", raising=False)
    load_dotenv_file(tmp_path / ".env")
    assert (os.environ["SPACED_TEST"], os.environ["SINGLE_TEST"]) == ("value with spaces", "single")
