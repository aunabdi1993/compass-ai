"""Thumbs up/down on coach replies, saved with the message."""

import streamlit as st


def _save_feedback(store, message: dict, key: str) -> None:
    value = st.session_state.get(key)  # st.feedback: 0 = thumbs down, 1 = thumbs up, None = cleared
    message["feedback"] = value
    try:
        store.set_feedback(message["id"], {0: -1, 1: 1}.get(value))
    except Exception as exc:
        st.toast(f"Couldn't save your rating: {exc}")


def feedback_widget(store, message: dict) -> None:
    key = f"fb_{message['id']}"
    if key not in st.session_state and message.get("feedback") is not None:
        st.session_state[key] = message["feedback"]  # widget state is dropped when you change page
    st.feedback("thumbs", key=key, on_change=_save_feedback, args=(store, message, key))
