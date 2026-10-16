"""Compass: Streamlit entry point. Run with `streamlit run app.py`."""

import streamlit as st

from compass import auth
from compass.config import load_settings
from compass.db import Store
from compass.llm import (
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    OpenRouterClient,
    stream_reply,
    to_api_messages,
)
from compass.memory import SUMMARIES_IN_PROMPT, catch_up, end_conversation
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

    system = build_system_prompt(state.get("profile"), state.get("summaries", []))
    reply = stream_reply(llm, settings.model, system, to_api_messages(state["history"]))
    try:
        with st.chat_message("assistant"):
            text = st.write_stream(reply)
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

    state["history"].append({"role": "assistant", "content": text})
    try:
        store.add_message(state["conversation_id"], "assistant", text)
    except Exception as exc:
        st.warning(f"I couldn't save that reply to your history: {exc}")


def profile_page(store: Store) -> None:
    st.title("Your profile")
    st.caption(
        "Compass uses this in every conversation so you don't have to repeat yourself. "
        "Leave anything blank that you'd rather not share."
    )
    profile = st.session_state.get("profile") or {}
    with st.form("profile_form"):
        role = st.text_input("Current role", value=profile.get("role", ""))
        industry = st.text_input("Industry", value=profile.get("industry", ""))
        goals = st.text_area(
            "Career goals", value=profile.get("goals", ""), height=120, max_chars=3000,
            help="For example: promoted to senior within 12 months, or move into product.",
        )
        cv_text = st.text_area(
            "CV (paste the text)", value=profile.get("cv_text", ""), height=300, max_chars=20000
        )
        if st.form_submit_button("Save"):
            try:
                store.save_profile(role=role, industry=industry, goals=goals, cv_text=cv_text)
            except Exception as exc:
                st.error(f"Couldn't save your profile: {exc}")
            else:
                st.session_state["profile"] = store.get_profile()
                st.success("Saved.")


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
            st.warning(f"Couldn't load your profile and past sessions: {exc}")

    with st.sidebar:
        st.write(user.email)
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
        ]
    )
    page.run()


main()
