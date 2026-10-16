"""Profile, Documents and Privacy pages."""

import streamlit as st

from compass import auth
from compass.consent import CONSENT_VERSION
from compass.documents import (
    ALLOWED_EXTENSIONS,
    MAX_DOC_CHARS,
    MAX_UPLOAD_BYTES,
    PROMPT_BUDGET_CHARS,
    DocumentError,
    extract_text,
    select_for_prompt,
)

MAX_DOCUMENTS = 10


def profile_page(store) -> None:
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
            "CV (paste the text)", value=profile.get("cv_text", ""), height=300, max_chars=20000,
            help="Or upload your CV as a file on the Documents page.",
        )
        if st.form_submit_button("Save"):
            try:
                store.save_profile(role=role, industry=industry, goals=goals, cv_text=cv_text)
            except Exception as exc:
                st.error(f"Couldn't save your profile: {exc}")
            else:
                st.session_state["profile"] = store.get_profile()
                st.success("Saved.")


def _refresh_documents(store) -> None:
    st.session_state["documents"] = store.list_documents()


def _toggle_document(store, document_id: str, key: str) -> None:
    try:
        store.set_document_enabled(document_id, bool(st.session_state[key]))
        _refresh_documents(store)
    except Exception as exc:
        st.toast(f"Couldn't update that document: {exc}")


def documents_page(store) -> None:
    st.title("Your documents")
    st.caption(
        "Add things Compass should know about: your CV, a job description, performance review "
        "notes, a development plan. Compass reads the documents that are switched on in every "
        "conversation and refers to them by name, so its advice stays relevant to you."
    )
    st.info(
        "Please don't upload confidential employer documents or other people's personal details. "
        "Only the text is kept, not the original file."
    )
    documents = st.session_state.get("documents", [])

    uploader_key = f"doc_upload_{st.session_state.get('doc_upload_n', 0)}"
    with st.form("upload_form"):
        files = st.file_uploader(
            f"Upload files ({', '.join(ALLOWED_EXTENSIONS)}; up to {MAX_UPLOAD_BYTES // 1024 // 1024} MB each)",
            type=list(ALLOWED_EXTENSIONS),
            accept_multiple_files=True,
            key=uploader_key,
        )
        submitted = st.form_submit_button("Add to Compass")
    if submitted and files:
        added = 0
        for uploaded in files:
            if len(documents) + added >= MAX_DOCUMENTS:
                st.error(f"You can keep up to {MAX_DOCUMENTS} documents. Remove one to add more.")
                break
            try:
                doc = extract_text(uploaded.name, uploaded.getvalue())
                store.add_document(doc.name, doc.text, doc.truncated)
            except DocumentError as exc:
                st.error(f"{uploaded.name}: {exc}")
            except Exception as exc:
                st.error(f"{uploaded.name}: couldn't save it ({exc}).")
            else:
                added += 1
                if doc.truncated:
                    st.warning(
                        f"{uploaded.name} is long, so only the first {MAX_DOC_CHARS:,} characters were kept."
                    )
        if added:
            _refresh_documents(store)
            st.session_state["doc_upload_n"] = st.session_state.get("doc_upload_n", 0) + 1
            st.session_state["doc_flash"] = f"Added {added} document{'s' if added != 1 else ''}."
            st.rerun()
    if flash := st.session_state.pop("doc_flash", None):
        st.success(flash)

    documents = st.session_state.get("documents", [])
    if not documents:
        st.write("No documents yet.")
        return

    included, left_out = select_for_prompt(documents)
    used = sum(len(d["content"]) for d in included)
    st.progress(min(used / PROMPT_BUDGET_CHARS, 1.0), text=f"Context in use: {used:,} of {PROMPT_BUDGET_CHARS:,} characters")
    if left_out:
        st.warning(
            "These didn't fit, so Compass can't see them right now: "
            + ", ".join(left_out)
            + ". Switch off or remove other documents to make room."
        )
    elif any(d["clipped"] for d in included):
        st.warning("The oldest document is partly cut to fit. Switch off or remove documents to make room.")

    for doc in documents:
        with st.container(border=True):
            left, right = st.columns([5, 1])
            toggle_key = f"doc_on_{doc['id']}"
            st.session_state.setdefault(toggle_key, bool(doc["enabled"]))
            left.toggle(
                doc["name"], key=toggle_key,
                on_change=_toggle_document, args=(store, doc["id"], toggle_key),
            )
            note = f"{doc['char_count']:,} characters" + (" (cut short)" if doc["truncated"] else "")
            left.caption(note)
            if right.button("Remove", key=f"doc_rm_{doc['id']}"):
                try:
                    store.delete_document(doc["id"])
                except Exception as exc:
                    st.error(f"Couldn't remove it: {exc}")
                else:
                    st.session_state.pop(toggle_key, None)
                    _refresh_documents(store)
                    st.rerun()


def privacy_page(store, client) -> None:
    st.title("Privacy")
    consent = st.session_state.get("consent") or {}
    st.write(
        f"You agreed to how Compass uses your information (version {consent.get('version', CONSENT_VERSION)}). "
        "Your messages, profile and documents are sent to an AI model provider each time you chat."
    )

    st.subheader("Improving Compass")
    opt_in = st.toggle(
        "Allow my chats to be used, with names, emails and company names removed, to improve "
        "and train Compass.",
        value=bool(consent.get("training_opt_in")),
        key="training_toggle",
    )
    if opt_in != bool(consent.get("training_opt_in")):
        try:
            store.set_training_opt_in(opt_in)
        except Exception as exc:
            st.error(f"Couldn't save that choice: {exc}")
        else:
            st.session_state["consent"] = {**consent, "training_opt_in": opt_in}
            st.toast("Saved.")

    st.subheader("Delete my data")
    st.write(
        "This permanently removes all of your conversations, session summaries, documents, "
        "profile and consent record. It can't be undone. You will be signed out."
    )
    with st.form("delete_form"):
        confirm = st.text_input("Type DELETE to confirm")
        if st.form_submit_button("Delete everything", type="primary"):
            if confirm.strip() != "DELETE":
                st.error("Type DELETE (in capitals) to confirm.")
            else:
                try:
                    store.delete_my_data()
                except Exception as exc:
                    st.error(f"Couldn't delete your data: {exc} Nothing was changed, so please try again.")
                else:
                    auth.sign_out(client)
                    st.session_state["notice"] = (
                        "Your conversations, documents and profile have been deleted. "
                        "Your sign-in email still exists; ask us if you'd like that removed too."
                    )
                    st.rerun()
