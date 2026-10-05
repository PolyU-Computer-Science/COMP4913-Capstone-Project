"""AI topic + field extraction service tests (6B)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from email_assistant.core.extraction import ExtractionResult, FakeExtractionClient, format_fields_prompt
from email_assistant.core.extraction_service import ExtractionService

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.setenv("SQLITE_EMAIL_DB", str(tmp_path / "emails.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    store.clear()
    yield
    store.clear()


TOPICS = [
    {"id": 1, "name": "Refund", "status": "active"},
    {"id": 2, "name": "Technical Issue", "status": "active"},
]

FIELDS = [
    {"id": 17, "name": "priority", "type": "select", "options": "Low,Medium,High", "status": "active"},
    {"id": 21, "name": "order_id", "type": "text", "status": "active"},
    {"id": 22, "name": "customer_count", "type": "number", "status": "active"},
    {"id": 23, "name": "requires_callback", "type": "boolean", "status": "active"},
]


def _service(result: ExtractionResult) -> ExtractionService:
    return ExtractionService(FakeExtractionClient(result))


def test_valid_topic_resolved() -> None:
    outcome = _service(ExtractionResult(topic="refund")).extract("email", TOPICS, FIELDS)
    assert outcome.topic_resolved is True
    assert outcome.topic == "Refund"
    assert outcome.topic_id == 1


def test_unknown_topic_not_assigned() -> None:
    outcome = _service(ExtractionResult(topic="made_up_topic")).extract("email", TOPICS, FIELDS)
    assert outcome.topic_resolved is False
    assert outcome.topic_id is None
    assert outcome.topic_raw == "made_up_topic"


def test_disabled_topic_not_assigned() -> None:
    topics = [{"id": 1, "name": "Refund", "status": "disabled"}]
    outcome = _service(ExtractionResult(topic="refund")).extract("email", topics, FIELDS)
    assert outcome.topic_resolved is False
    assert outcome.topic_id is None


def test_valid_fields_accepted() -> None:
    result = ExtractionResult(
        topic="refund",
        fields=[
            {"field_id": 17, "value": "High"},
            {"field_id": 21, "value": "A1234"},
            {"field_id": 22, "value": 120},
            {"field_id": 23, "value": True},
        ],
    )
    outcome = _service(result).extract("email", TOPICS, FIELDS)
    assert outcome.fields_accepted == 4
    assert outcome.fields_rejected == 0


def test_invalid_fields_rejected_partial_success() -> None:
    result = ExtractionResult(
        topic="refund",
        fields=[
            {"field_id": 17, "value": "High"},          # valid
            {"field_id": 22, "value": "many"},           # invalid (number)
            {"field_id": 999, "value": "x"},             # foreign field
        ],
    )
    outcome = _service(result).extract("email", TOPICS, FIELDS)
    assert outcome.fields_accepted == 1
    assert outcome.fields_rejected == 2
    accepted = outcome.accepted_values()
    assert accepted == {17: "High"}


def test_select_field_out_of_options_rejected() -> None:
    result = ExtractionResult(topic="refund", fields=[{"field_id": 17, "value": "Extreme"}])
    outcome = _service(result).extract("email", TOPICS, FIELDS)
    assert outcome.fields_accepted == 0
    assert outcome.fields_rejected == 1


def test_malformed_field_id_rejected() -> None:
    result = ExtractionResult(topic="refund", fields=[{"field_id": "not-an-int", "value": "x"}])
    outcome = _service(result).extract("email", TOPICS, FIELDS)
    assert outcome.fields_rejected == 1


def test_empty_extraction_handled() -> None:
    outcome = _service(ExtractionResult()).extract("email", TOPICS, FIELDS)
    assert outcome.topic == ""
    assert outcome.fields_accepted == 0


def test_extraction_failure_does_not_crash() -> None:
    class BoomClient:
        def extract(self, email_content, topics, fields):
            raise RuntimeError("boom")

    outcome = ExtractionService(BoomClient()).extract("email", TOPICS, FIELDS)
    assert outcome.fields == []
    assert outcome.topic == ""


def test_format_fields_prompt_uses_field_ids() -> None:
    prompt = format_fields_prompt(FIELDS)
    assert "ID: 17" in prompt
    assert "priority" in prompt
    assert "select [Low,Medium,High]" in prompt


def test_manual_field_not_overwritten_by_ai() -> None:
    import email_assistant.core

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: [
            {
                "sender": "a@x.com",
                "subject": "Refund",
                "body": "hi",
                "timestamp": "2026-09-01T10:00:00Z",
                "mailbox_id": mid,
            }
        ],
    )

    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    client.post(
        f"/api/mailboxes/{mailbox_id}/fields",
        json={"name": "priority", "type": "select", "options": "Low,Medium,High"},
    )

    # Manually set priority = Medium.
    import crewai

    monkeypatch.setattr(
        crewai.Crew,
        "kickoff",
        lambda self, inputs=None, **kwargs: SimpleNamespace(
            pydantic=SimpleNamespace(
                model_dump=lambda: {
                    "category": "question",
                    "topic": "refund",
                    "priority": "normal",
                    "summary": "s",
                    "custom": {},
                }
            ),
            raw="Draft",
        ),
    )

    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    email_id = client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0]["id"]
    client.post(f"/api/emails/{email_id}/process")

    field_id = client.get(f"/api/mailboxes/{mailbox_id}/fields").json()[0]["id"]
    client.put(
        f"/api/cases/{email_id}/fields",
        json={"values": {str(field_id): "Medium"}},
    )

    # Now simulate AI wanting to overwrite: directly test store protection.
    store.fill_ai_case_field_values(email_id, {field_id: json.dumps("High")})
    saved = store.get_case_field_values(email_id)
    assert json.loads(saved[field_id]) == "Medium"

    monkeypatch.undo()


def test_ai_extraction_fills_empty_field_only() -> None:
    import email_assistant.core
    import crewai

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: [
            {
                "sender": "a@x.com",
                "subject": "Refund",
                "body": "hi",
                "timestamp": "2026-09-01T10:00:00Z",
                "mailbox_id": mid,
            }
        ],
    )
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
            topic="refund",
            priority="normal",
            summary="s",
            custom_fields={"order_id": "ORD-1"},
            structured_valid=True,
            attempts=1,
        ),
    )

    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    client.post(
        f"/api/mailboxes/{mailbox_id}/fields",
        json={"name": "order_id", "type": "text"},
    )

    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    email_id = client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0]["id"]
    client.post(f"/api/emails/{email_id}/process")

    field_id = client.get(f"/api/mailboxes/{mailbox_id}/fields").json()[0]["id"]
    fields = client.get(f"/api/cases/{email_id}/fields").json()
    assert fields[0]["value"] == "ORD-1"

    monkeypatch.undo()
