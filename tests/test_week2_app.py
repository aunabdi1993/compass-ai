"""Week 2 behaviour through Streamlit's AppTest, with Supabase and the LLM faked."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import compass.auth
import compass.db
import compass.llm
from compass.consent import CONSENT_VERSION
from tests.fakes import FakeLLM, FakeStore

APP = str(Path(__file__).resolve().parent.parent / "app.py")
ENV = {"OPENROUTER_API_KEY": "k", "SUPABASE_URL": "http://x", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_a"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


def make_app(monkeypatch, llm, store):
    monkeypatch.setattr(compass.llm, "OpenRouterClient", lambda key, site_url=None: llm)
    monkeypatch.setattr(compass.db, "Store", lambda client, uid: store)
    user = SimpleNamespace(id="u1", email="a@example.com")
    monkeypatch.setattr(compass.auth, "current_user", lambda s: (object(), user))
    return AppTest.from_file(APP, default_timeout=20)


# consent -------------------------------------------------------------------
def test_consent_blocks_everything_until_agreed(monkeypatch):
    llm, store = FakeLLM(), FakeStore(consented=False)
    at = make_app(monkeypatch, llm, store).run()
    assert not at.exception
    assert at.title[0].value == "Welcome to Compass" and not at.chat_input
    assert "AI coach, not a human" in " ".join(m.value for m in at.markdown)

    at.button[0].click().run()  # Continue without ticking
    assert at.error and store.consent == {} and not at.chat_input
    assert llm.stream_calls == [] and llm.chat_calls == []  # nothing sent to the model


def test_consent_is_saved_with_separate_training_opt_in(monkeypatch):
    for tick_training in (False, True):
        store = FakeStore(consented=False)
        at = make_app(monkeypatch, FakeLLM(), store).run()
        at.checkbox[0].check()
        if tick_training:
            at.checkbox[1].check()
        at.button[0].click().run()
        assert store.consent == {"version": CONSENT_VERSION, "training_opt_in": tick_training}
        assert at.chat_input  # now in the app


def test_outdated_consent_version_asks_again(monkeypatch):
    store = FakeStore()
    store.consent = {"version": "old", "training_opt_in": True}
    at = make_app(monkeypatch, FakeLLM(), store).run()
    assert at.title[0].value == "Welcome to Compass"


# documents in context ----------------------------------------------------------
def test_enabled_documents_reach_the_prompt_and_disabled_ones_do_not(monkeypatch):
    llm, store = FakeLLM(), FakeStore()
    store.add_document("review.docx", "Q3 review: strong delivery, weak visibility.", False)
    store.add_document("old-cv.pdf", "Ancient history.", False)
    store.set_document_enabled("d2", False)
    at = make_app(monkeypatch, llm, store).run()
    at.chat_input[0].set_value("How do I get visible?").run()
    system = llm.stream_calls[0]["messages"][0]["content"]
    assert '<document name="review.docx">' in system and "weak visibility" in system
    assert "old-cv.pdf" not in system


# thumbs -------------------------------------------------------------------------
def thumbs_app(store, message):
    import streamlit as st

    from compass.feedback import feedback_widget

    feedback_widget(store, message)
    st.session_state["seen_feedback"] = message["feedback"]


def test_thumbs_are_saved_with_the_message():
    store = FakeStore()
    cid = store.create_conversation()
    message_id = store.add_message(cid, "assistant", "Here's a plan.")
    message = {"id": message_id, "feedback": None}
    at = AppTest.from_function(thumbs_app, args=(store, message), default_timeout=20).run()
    at.get("feedback")[0].set_value(1).run()  # thumbs up
    assert store.get_messages(cid)[0]["feedback"] == 1
    at.get("feedback")[0].set_value(0).run()  # changed their mind: thumbs down
    assert store.get_messages(cid)[0]["feedback"] == -1
    at.get("feedback")[0].set_value(None).run()  # cleared
    assert store.get_messages(cid)[0]["feedback"] is None


# privacy page ---------------------------------------------------------------------
def privacy_app(store, signed_out):
    from compass import auth
    from compass.pages import privacy_page

    auth.sign_out = lambda client: signed_out.append(True)
    import streamlit as st

    st.session_state.setdefault("consent", store.consent)
    privacy_page(store, object())


def test_delete_my_data_needs_confirmation_then_wipes_everything():
    store, signed_out = FakeStore(), []
    cid = store.create_conversation()
    store.add_message(cid, "user", "hi")
    store.add_document("cv.pdf", "my cv", False)
    store.save_profile(role="Analyst")
    at = AppTest.from_function(privacy_app, args=(store, signed_out), default_timeout=20).run()

    at.button[0].click().run()  # nothing typed
    assert at.error and not store.deleted
    at.text_input[0].set_value("delete")
    at.button[0].click().run()  # wrong case
    assert not store.deleted
    at.text_input[0].set_value("DELETE")
    at.button[0].click().run()
    assert store.deleted and signed_out
    assert store.conversations == {} and store.documents == [] and store.profile == {}
    assert "deleted" in at.session_state["notice"]


def test_training_opt_in_can_be_changed_later():
    store = FakeStore()
    at = AppTest.from_function(privacy_app, args=(store, []), default_timeout=20).run()
    at.toggle[0].set_value(True).run()
    assert store.consent["training_opt_in"] is True
    at.toggle[0].set_value(False).run()
    assert store.consent["training_opt_in"] is False


# documents page ----------------------------------------------------------------------
def documents_app(store):
    import streamlit as st

    from compass.pages import documents_page

    st.session_state.setdefault("documents", store.list_documents())
    documents_page(store)


def test_documents_page_toggle_and_remove():
    store = FakeStore()
    store.add_document("cv.pdf", "x" * 500, False)
    store.add_document("jd.txt", "y" * 500, False)
    at = AppTest.from_function(documents_app, args=(store,), default_timeout=20).run()
    assert not at.exception and len(at.toggle) == 2

    first = at.toggle[0]
    name = first.label
    first.set_value(False).run()
    assert {d["name"]: d["enabled"] for d in store.documents}[name] is False

    [b for b in at.button if b.label == "Remove"][0].click().run()
    assert len(store.documents) == 1
