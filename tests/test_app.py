"""End-to-end through Streamlit's AppTest, with Supabase and the LLM faked."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import compass.auth
import compass.db
from tests.fakes import FakeLLM, FakeStore

APP = str(Path(__file__).resolve().parent.parent / "app.py")
ENV = {"OPENROUTER_API_KEY": "k", "SUPABASE_URL": "http://x", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_a"}


@pytest.fixture
def env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


def make_app(monkeypatch, llm, store, signed_in=True):
    import compass.llm

    monkeypatch.setattr(compass.llm, "OpenRouterClient", lambda key, site_url=None: llm)
    monkeypatch.setattr(compass.db, "Store", lambda client, uid: store)
    user = SimpleNamespace(id="u1", email="a@example.com") if signed_in else None
    monkeypatch.setattr(compass.auth, "current_user", lambda s: (object(), user))
    return AppTest.from_file(APP, default_timeout=15)


def test_missing_config_shows_error(monkeypatch):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    at = AppTest.from_file(APP).run()
    assert "Missing configuration" in at.error[0].value


def test_signed_out_sees_login(env, monkeypatch):
    monkeypatch.setattr(compass.auth, "login_screen", lambda c: __import__("streamlit").write("LOGIN"))
    at = make_app(monkeypatch, FakeLLM(), FakeStore(), signed_in=False).run()
    assert not at.exception and at.markdown[0].value == "LOGIN"
    assert not at.chat_input


def test_chat_saves_and_remembers(env, monkeypatch):
    llm, store = FakeLLM(), FakeStore()
    store.profile = {"role": "Analyst"}
    at = make_app(monkeypatch, llm, store).run()
    assert not at.exception

    at.chat_input[0].set_value("How do I get promoted?").run()
    assert not at.exception
    assert [m["role"] for m in store.conversations["c1"]["messages"]] == ["user", "assistant"]
    assert store.conversations["c1"]["messages"][1]["content"] == "Hello there."
    assert "Current role:\nAnalyst" in llm.stream_calls[0]["messages"][0]["content"]

    # End the session: a summary is written, and the next session's prompt carries it.
    [b for b in at.sidebar.button if b.label == "End session"][0].click().run()
    assert store.conversations["c1"]["summary"]
    at.chat_input[0].set_value("Hi again").run()
    assert "- a\n- b" in llm.stream_calls[-1]["messages"][0]["content"]
    assert store.conversations["c2"]["messages"][0]["content"] == "Hi again"


def test_daily_limit_blocks_without_calling_model(env, monkeypatch):
    llm, store = FakeLLM(), FakeStore()
    store.today = 50
    at = make_app(monkeypatch, llm, store).run()
    at.chat_input[0].set_value("hello").run()
    assert at.warning and llm.stream_calls == []
    assert store.conversations == {}
