"""Compass: Streamlit entry point. Run with `streamlit run app.py`."""

import streamlit as st

from compass import auth
from compass.config import load_settings
from compass.consent import consent_screen, needs_consent
from compass.db import Store
from compass.documents import select_for_prompt
from compass.feedback import feedback_widget
from compass.llm import (
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    OpenRouterClient,
    stream_reply,
    to_api_messages,
)
from compass.memory import SUMMARIES_IN_PROMPT, catch_up, end_conversation
from compass.pages import documents_page, privacy_page, profile_page
from compass.prompts import build_system_prompt

st.set_page_config(page_title="Compass", page_icon="🧭")

GREETING = (
    "Hi, I'm Compass, an AI career coach. Tell me a bit about your current role and "
    "what you'd like to work on: a review, a skill, a promotion, or a move. "
    "Please don't share confidential employer information or colleagues' personal details."
)


@st.cache_resource
def llm_client(api_key: str, site_url: str | None) -> OpenRouterClient:
    return OpenRouterClient(api_key, site_url)


def _load_context(store: Store) -> None:
    st.session_state["profile"] = store.get_profile()
    st.session_state["summaries"] = store.recent_summaries(SUMMARIES_IN_PROMPT)
    st.session_state["documents"] = store.list_documents()


def chat_page(settings, store: Store, llm: OpenRouterClient) -> None:
    state = st.session_state
    state.setdefault("history", [])
    st.title("Compass")

    if not state["history"]:
        with st.chat_message("assistant"):
            st.write(GREETING)
    for message in state["history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant" and message.get("id"):
                feedback_widget(store, message)

    prompt = st.chat_input("What's on your mind?")
    if not prompt:
        return

    if store.count_user_messages_today() >= settings.daily_message_limit:
        st.warning("You've reached today's message limit. Come back tomorrow.")
        return

    try:
        if not state.get("conversation_id"):
            state["conversation_id"] = store.create_conversation()
        store.add_message(state["conversation_id"], "user", prompt)
    except Exception as exc:
        st.error(f"Couldn't save your message, so I haven't sent it: {exc}")
        return
    state["history"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    documents, _left_out = select_for_prompt(state.get("documents", []))
    system = build_system_prompt(state.get("profile"), state.get("summaries", []), documents)
    reply = stream_reply(llm, settings.model, system, to_api_messages(state["history"]))
    entry = {"role": "assistant", "content": "", "id": None, "feedback": None}
    try:
        with st.chat_message("assistant"):
            entry["content"] = st.write_stream(reply)
            try:
                entry["id"] = store.add_message(state["conversation_id"], "assistant", entry["content"])
            except Exception as exc:
                st.warning(f"I couldn't save that reply to your history: {exc}")
            else:
                feedback_widget(store, entry)
    except LLMRateLimitError:
        st.error("Compass is busy right now. Please try again in a minute.")
        return
    except LLMConnectionError:
        st.error("Couldn't reach the coaching service. Check your connection and try again.")
        return
    except LLMError as exc:
        code = f" ({exc.status_code})" if exc.status_code else ""
        st.error(f"The coaching service returned an error{code}. Please try again.")
        return

    state["history"].append(entry)


def main() -> None:
    try:
        settings = load_settings(st.secrets)
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    client, user = auth.current_user(settings)
    if user is None:
        auth.login_screen(client)
        st.stop()

    store = Store(client, user.id)
    llm = llm_client(settings.openrouter_api_key, settings.site_url)
    state = st.session_state

    # Nothing is loaded or sent to the model until the user has agreed.
    if "consent" not in state:
        try:
            state["consent"] = store.get_consent()
        except Exception as exc:
            st.error(f"Couldn't check your privacy settings, so I haven't continued: {exc}")
            st.stop()
    if needs_consent(state["consent"]):
        consent_screen(store)
        st.stop()

    if "profile" not in state:
        try:
            _load_context(store)
            # Summarise earlier sessions that ended when the tab was closed.
            with st.spinner("Catching up on your last session..."):
                catch_up(store, llm, settings.model, state.get("conversation_id"))
            state["summaries"] = store.recent_summaries(SUMMARIES_IN_PROMPT)
        except Exception as exc:
            state.setdefault("profile", {})
            state.setdefault("summaries", [])
            state.setdefault("documents", [])
            st.warning(f"Couldn't load your profile and past sessions: {exc}")

    with st.sidebar:
        st.text(user.email)  # not st.write: markdown would turn it into a mailto link
        # Not disabled when empty: this renders before the chat page handles a new
        # message, so a disabled state would be stale for the first exchange.
        if st.button("End session",
                     help="Compass writes itself a short note so it remembers this next time."):
            if state.get("conversation_id"):
                with st.spinner("Saving a note for next time..."):
                    try:
                        end_conversation(store, llm, settings.model, state["conversation_id"])
                        state["summaries"] = store.recent_summaries(SUMMARIES_IN_PROMPT)
                    except Exception as exc:
                        st.warning(f"Couldn't save the note: {exc} It will be retried next login.")
            state["history"] = []
            state["conversation_id"] = None
            st.rerun()
        if st.button("Sign out"):
            auth.sign_out(client)
            st.rerun()

    page = st.navigation(
        [
            st.Page(lambda: chat_page(settings, store, llm), title="Coach", url_path="coach", default=True),
            st.Page(lambda: profile_page(store), title="Profile", url_path="profile"),
            st.Page(lambda: documents_page(store), title="Documents", url_path="documents"),
            st.Page(lambda: privacy_page(store, client), title="Privacy", url_path="privacy"),
        ]
    )
    page.run()


main()
