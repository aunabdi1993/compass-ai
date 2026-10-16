"""Supabase email login using the one-time code in the sign-in email.

Streamlit reruns the script on every interaction and has no access to URL fragments,
so we use the emailed 6-digit code (same email as the magic link) instead of
redirecting back to the app.
"""

import streamlit as st
from supabase import create_client


def _client(settings):
    # One Supabase client per browser session; a shared one would mix users' tokens.
    if "sb_client" not in st.session_state:
        st.session_state["sb_client"] = create_client(
            settings.supabase_url, settings.supabase_key
        )
    return st.session_state["sb_client"]


def current_user(settings):
    """Return (client, user) if signed in, else (client, None)."""
    client = _client(settings)
    return client, st.session_state.get("user")


def send_code(client, email: str) -> None:
    client.auth.sign_in_with_otp({"email": email, "options": {"should_create_user": True}})


def verify_code(client, email: str, code: str):
    response = client.auth.verify_otp({"email": email, "token": code.strip(), "type": "email"})
    if not response.user:
        raise ValueError("That code didn't work.")
    st.session_state["user"] = response.user
    return response.user


def sign_out(client) -> None:
    try:
        client.auth.sign_out()
    finally:
        st.session_state.clear()


def login_screen(client) -> None:
    st.title("Compass")
    st.caption("Your AI career coach. Sign in with your email, no password needed.")

    email = st.session_state.get("login_email")
    if not email:
        with st.form("email_form"):
            entered = st.text_input("Email address")
            if st.form_submit_button("Email me a code") and entered.strip():
                try:
                    send_code(client, entered.strip())
                except Exception as exc:
                    st.error(f"Couldn't send the email: {exc}")
                else:
                    st.session_state["login_email"] = entered.strip()
                    st.rerun()
        return

    st.info(f"We sent a code to **{email}**. It can take a minute to arrive.")
    with st.form("code_form"):
        code = st.text_input("6-digit code", max_chars=10)
        if st.form_submit_button("Sign in") and code.strip():
            try:
                verify_code(client, email, code)
            except Exception:
                st.error("That code didn't work. Check it and try again, or request a new one.")
            else:
                st.rerun()
    if st.button("Use a different email"):
        st.session_state.pop("login_email", None)
        st.rerun()
