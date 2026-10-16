import importlib.util
import sys
from pathlib import Path

import pytest

presidio = pytest.importorskip("presidio_analyzer")
spacy = pytest.importorskip("spacy")

try:
    spacy.load("en_core_web_sm")
except OSError:  # model not installed
    pytest.skip("en_core_web_sm not installed", allow_module_level=True)

from compass.anonymise import Anonymiser  # noqa: E402


@pytest.fixture(scope="module")
def anonymiser():
    return Anonymiser("en_core_web_sm")


def test_removes_names_company_email_phone_and_url(anonymiser):
    text = (
        "Hi, I'm Sarah Jones and I work at Acme Corp. My manager Tom Becker said to email "
        "sarah.jones@acme.com or call 07700 900123. Profile: https://linkedin.com/in/sarahj"
    )
    out = anonymiser.anonymise(text)
    for secret in ("Sarah", "Jones", "Acme", "Tom Becker", "sarah.jones@acme.com", "07700", "linkedin.com"):
        assert secret not in out, (secret, out)
    for tag in ("<PERSON>", "<COMPANY>", "<EMAIL>", "<URL>"):
        assert tag in out


def test_keeps_the_career_content(anonymiser):
    out = anonymiser.anonymise("I want a promotion to senior analyst and my review is in two weeks.")
    assert "promotion" in out and "review is in two weeks" in out


def test_known_terms_are_removed_even_if_the_model_misses_them():
    anon = Anonymiser("en_core_web_sm", extra_terms=["Zorblax"])
    assert "Zorblax" not in anon.anonymise("I joined zorblax last year. ZORBLAX is great.")


def test_empty_text_passes_through(anonymiser):
    assert anonymiser.anonymise("") == ""


def load_export_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "export_training_data.py"
    spec = importlib.util.spec_from_file_location("export_training_data", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_training_data"] = module
    spec.loader.exec_module(module)
    return module


def test_export_only_includes_opted_in_users_and_hides_identities(anonymiser):
    export = load_export_script()
    consents = [{"user_id": "u1", "training_opt_in": True}, {"user_id": "u2", "training_opt_in": False}]
    conversations = [
        {"id": "c1", "user_id": "u1"},
        {"id": "c2", "user_id": "u2"},  # did not opt in
        {"id": "c3", "user_id": "u1"},  # no coach reply: skipped
    ]
    messages = [
        {"id": 2, "conversation_id": "c1", "role": "assistant", "content": "Tell me more.", "feedback": 1},
        {"id": 1, "conversation_id": "c1", "role": "user", "content": "I'm Sarah Jones at Acme Corp.", "feedback": None},
        {"id": 3, "conversation_id": "c2", "role": "user", "content": "secret chat", "feedback": None},
        {"id": 4, "conversation_id": "c2", "role": "assistant", "content": "ok", "feedback": None},
        {"id": 5, "conversation_id": "c3", "role": "user", "content": "unanswered", "feedback": None},
    ]
    dataset = export.build_dataset(consents, conversations, messages, anonymiser.anonymise)
    assert len(dataset) == 1
    turns = dataset[0]["messages"]
    assert [t["role"] for t in turns] == ["user", "assistant"]  # ordered by id
    assert "Sarah" not in turns[0]["content"] and "Acme" not in turns[0]["content"]
    assert turns[1]["feedback"] == 1 and "feedback" not in turns[0]
    assert "u1" not in str(dataset) and "secret chat" not in str(dataset)
