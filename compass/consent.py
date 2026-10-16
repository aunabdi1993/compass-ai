"""First-login consent screen, plus the Privacy page controls."""

import streamlit as st

CONSENT_VERSION = "2026-10-v1"

WHAT_WE_DO = """
**Before you start, here is how Compass works with your information.**

- **Compass is an AI coach, not a human.** It can be wrong. It does not give legal, medical
  or financial advice. For a workplace dispute, speak to ACAS, a union rep or an employment
  lawyer. If you are struggling, speak to your GP, someone you trust, or Samaritans (116 123).
- **What we store:** your conversations, the profile and documents you add, short summaries of
  past sessions, and your thumbs up/down ratings. They are tied to your sign-in email and used
  only to give you coaching that remembers you.
- **Who processes it:** your messages, profile and documents are sent to an AI model provider
  (via OpenRouter) each time you chat, so the coach can reply.
- **Please don't share** confidential employer information, or other people's personal details.
- **You are in control:** you can switch documents off or remove them, and delete all of your
  data at any time from the Privacy page.
"""


def consent_screen(store) -> None:
    st.title("Welcome to Compass")
    st.markdown(WHAT_WE_DO)
    with st.form("consent_form"):
        agreed = st.checkbox("I understand how Compass uses my information, and I agree.")
        training = st.checkbox(
            "Optional: allow my chats to be used, after names, emails and company names "
            "are removed, to improve Compass and train future versions.",
            help="This is separate from the box above. Leaving it unticked has no effect on "
            "how Compass works for you. You can change your mind on the Privacy page.",
        )
        if st.form_submit_button("Continue"):
            if not agreed:
                st.error("Please tick the first box to continue.")
            else:
                try:
                    store.save_consent(CONSENT_VERSION, training)
                except Exception as exc:
                    st.error(f"Couldn't save your choice: {exc}")
                else:
                    st.session_state["consent"] = {"version": CONSENT_VERSION, "training_opt_in": training}
                    st.rerun()


def needs_consent(consent: dict | None) -> bool:
    return not consent or consent.get("version") != CONSENT_VERSION
