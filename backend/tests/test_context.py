"""Topic resolution + custom field runtime tests.

These verify that mailbox topics actually constrain the classifier output and
that custom field values are typed, validated, and mailbox-scoped.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from email_assistant.core.field_validation import validate_field_value
from email_assistant.core.topics import resolve_topic

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.setenv("SQLITE_EMAIL_DB", str(tmp_path / "emails.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    store.clear()
    yield
    store.clear()


def _fake_kickoff(self, inputs=None, **kwargs):  # noqa: ANN001
    return SimpleNamespace(raw="Draft")


def _fake_classify(self, email_content, topics, fields=None):  # noqa: ANN001
    from email_assistant.core.structured_classification import (
        ClassificationOutcome,
    )

    # Echo a topic that maps to a known topic name.
    return ClassificationOutcome(
        category="question",
        topic="password_reset",
        priority="normal",
        summary="summary",
        structured_valid=True,
        attempts=1,
    )


def _create_mailbox(name: str) -> int:
    return client.post(
        "/api/mailboxes", json={"name": name, "address": f"{name.lower()}@x.com"}
    ).json()["id"]


def _seed_email(monkeypatch, mailbox_id: int) -> str:
    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: [
            {
                "sender": "a@x.com",
                "subject": "Test",
                "body": "hi",
                "timestamp": "2026-09-01T10:00:00Z",
                "mailbox_id": mid,
            }
        ],
    )
    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    return client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0][
        "id"
    ]


def _seed_and_process(monkeypatch, mailbox_id: int, topic: str) -> str:
    import crewai

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)
    from email_assistant.core.structured_classification import StructuredClassifier

    monkeypatch.setattr(StructuredClassifier, "classify", _fake_classify)
    email_id = _seed_email(monkeypatch, mailbox_id)
    client.post(f"/api/emails/{email_id}/process")
    return email_id


# ---- topic resolution unit tests ----

def test_resolve_topic_matches_case_insensitive_and_normalized() -> None:
    topics = [
        {"id": 1, "name": "Password Reset", "status": "active"},
        {"id": 2, "name": "refund", "status": "active"},
    ]
    topic_id, canonical = resolve_topic(topics, "password_reset")
    assert topic_id == 1
    assert canonical == "Password Reset"

    topic_id, canonical = resolve_topic(topics, "  REFUND  ")
    assert topic_id == 2
    assert canonical == "refund"


def test_resolve_topic_returns_none_for_unknown() -> None:
    topics = [{"id": 1, "name": "refund", "status": "active"}]
    topic_id, canonical = resolve_topic(topics, "totally_made_up_topic")
    assert topic_id is None
    assert canonical == "totally_made_up_topic"


def test_resolve_topic_ignores_disabled_topics() -> None:
    topics = [{"id": 1, "name": "refund", "status": "disabled"}]
    topic_id, _ = resolve_topic(topics, "refund")
    assert topic_id is None


def test_topic_is_resolved_against_mailbox_topics(monkeypatch) -> None:
    mailbox_id = _create_mailbox("Support")
    client.post(
        f"/api/mailboxes/{mailbox_id}/topics",
        json={"name": "Password Reset", "description": "account access"},
    )

    email_id = _seed_and_process(monkeypatch, mailbox_id, "password_reset")

    case = client.get(f"/api/cases?mailbox_id={mailbox_id}").json()["cases"][0]
    assert case["id"] == email_id
    assert case["topic_id"] is not None
    assert case["classification"]["topic"] == "Password Reset"
    assert case["topic_raw"] == "password_reset"


def test_invalid_topic_is_not_resolved_to_a_topic_id(monkeypatch) -> None:
    mailbox_id = _create_mailbox("Support")
    client.post(
        f"/api/mailboxes/{mailbox_id}/topics",
        json={"name": "Refund", "description": "refunds"},
    )

    import crewai

    monkeypatch.setattr(
        crewai.Crew,
        "kickoff",
        lambda self, inputs=None, **kwargs: SimpleNamespace(raw="Draft"),
    )
    from email_assistant.core.structured_classification import (
        ClassificationOutcome,
        StructuredClassifier,
    )

    monkeypatch.setattr(
        StructuredClassifier,
        "classify",
        lambda self, email_content, topics, fields=None: ClassificationOutcome(
            category="question",
            topic="payment_cancellation_dispute",
            priority="normal",
            summary="s",
            structured_valid=True,
            attempts=1,
        ),
    )

    email_id = _seed_email(monkeypatch, mailbox_id)
    client.post(f"/api/emails/{email_id}/process")

    case = client.get(f"/api/cases?mailbox_id={mailbox_id}").json()["cases"][0]
    assert case["topic_id"] is None
    assert case["topic_raw"] == "payment_cancellation_dispute"


# ---- field validation unit tests ----

def test_field_value_validation_by_type() -> None:
    assert validate_field_value({"name": "Order ID", "type": "text"}, "ORD-1")[0]
    assert not validate_field_value({"name": "Order ID", "type": "text"}, 123)[0]

    assert validate_field_value({"name": "Budget", "type": "number"}, 3500)[0]
    assert not validate_field_value({"name": "Budget", "type": "number"}, "x")[0]

    assert validate_field_value({"name": "Flag", "type": "boolean"}, True)[0]
    assert not validate_field_value({"name": "Flag", "type": "boolean"}, "yes")[0]


def test_select_field_must_match_options() -> None:
    field = {"name": "Severity", "type": "select", "options": "low,medium,high"}
    assert validate_field_value(field, "high")[0]
    assert not validate_field_value(field, "extreme")[0]


def test_required_field_rejects_none() -> None:
    assert not validate_field_value({"name": "Order ID", "type": "text", "required": True}, None)[0]
    assert validate_field_value({"name": "Order ID", "type": "text", "required": False}, None)[0]


# ---- case fields HTTP tests ----

def test_case_fields_roundtrip(monkeypatch) -> None:
    mailbox_id = _create_mailbox("Support")
    field = client.post(
        f"/api/mailboxes/{mailbox_id}/fields",
        json={"name": "Order ID", "type": "text", "required": False},
    ).json()
    field_id = field["id"]

    email_id = _seed_and_process(monkeypatch, mailbox_id, "refund")

    # Empty initially.
    fields = client.get(f"/api/cases/{email_id}/fields").json()
    assert len(fields) == 1
    assert fields[0]["value"] is None

    # Bulk update.
    updated = client.put(
        f"/api/cases/{email_id}/fields",
        json={"values": {str(field_id): "ORD-8821"}},
    )
    assert updated.status_code == 200
    assert updated.json()[0]["value"] == "ORD-8821"


def test_case_fields_reject_cross_mailbox_field(monkeypatch) -> None:
    support_id = _create_mailbox("Support")
    sales_id = _create_mailbox("Sales")

    field = client.post(
        f"/api/mailboxes/{sales_id}/fields",
        json={"name": "Company", "type": "text"},
    ).json()
    sales_field_id = field["id"]

    email_id = _seed_and_process(monkeypatch, support_id, "refund")

    response = client.put(
        f"/api/cases/{email_id}/fields",
        json={"values": {str(sales_field_id): "Acme"}},
    )
    assert response.status_code == 400


def test_case_fields_reject_invalid_type(monkeypatch) -> None:
    mailbox_id = _create_mailbox("Support")
    field = client.post(
        f"/api/mailboxes/{mailbox_id}/fields",
        json={"name": "Budget", "type": "number"},
    ).json()
    field_id = field["id"]

    email_id = _seed_and_process(monkeypatch, mailbox_id, "refund")

    response = client.put(
        f"/api/cases/{email_id}/fields",
        json={"values": {str(field_id): "not-a-number"}},
    )
    assert response.status_code == 422


def test_case_field_values_persist_as_json(monkeypatch) -> None:
    mailbox_id = _create_mailbox("Support")
    field = client.post(
        f"/api/mailboxes/{mailbox_id}/fields",
        json={"name": "Severity", "type": "select", "options": "low,high"},
    ).json()
    field_id = field["id"]

    email_id = _seed_and_process(monkeypatch, mailbox_id, "refund")
    client.put(
        f"/api/cases/{email_id}/fields",
        json={"values": {str(field_id): "high"}},
    )

    saved = store.get_case_field_values(email_id)
    assert json.loads(saved[field_id]) == "high"
