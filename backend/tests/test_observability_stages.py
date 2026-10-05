"""Observability stage metadata tests (7B)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from email_assistant.core.observability import Observer
from email_assistant.core.observability_store import ObservabilityStore

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.setenv("SQLITE_EMAIL_DB", str(tmp_path / "emails.db"))
    monkeypatch.setenv("OBSERVABILITY_DB", str(tmp_path / "observability.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    store.clear()
    ObservabilityStore().clear()
    yield
    store.clear()


def _fake_kickoff(self, inputs=None, **kwargs):  # noqa: ANN001
    return SimpleNamespace(
        raw="Draft",
        usage_metrics={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )


def _fake_classify(self, email_content, topics, fields=None):  # noqa: ANN001
    from email_assistant.core.structured_classification import (
        ClassificationOutcome,
    )

    return ClassificationOutcome(
        category="question",
        topic="refund",
        topic_resolved=True,
        priority="normal",
        summary="s",
        custom_fields={},
        structured_valid=True,
        attempts=1,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )


def _mock_pipeline(monkeypatch) -> None:
    import crewai

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)
    from email_assistant.core.structured_classification import StructuredClassifier

    monkeypatch.setattr(StructuredClassifier, "classify", _fake_classify)


def _process_support_email(monkeypatch) -> tuple[int, str]:
    _mock_pipeline(monkeypatch)

    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: [
            {
                "sender": "a@x.com",
                "subject": "Refund",
                "body": "Can I get a refund?",
                "timestamp": "2026-09-01T10:00:00Z",
                "mailbox_id": mid,
            }
        ],
    )

    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    client.post(
        f"/api/mailboxes/{mailbox_id}/topics",
        json={"name": "Refund", "description": "refunds"},
    )
    client.post(
        f"/api/mailboxes/{mailbox_id}/fields",
        json={"name": "priority", "type": "select", "options": "Low,High"},
    )

    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    email_id = client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0]["id"]
    client.post(f"/api/emails/{email_id}/process")
    return mailbox_id, email_id


def test_email_fetch_stage_recorded(monkeypatch) -> None:
    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core, "fetch_emails", lambda: []
    )
    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})

    runs = ObservabilityStore().list_runs(mailbox_id=mailbox_id)
    stages = {r["stage"] for r in runs}
    assert "email_fetch" in stages


def test_processing_stages_recorded(monkeypatch) -> None:
    mailbox_id, _ = _process_support_email(monkeypatch)
    runs = ObservabilityStore().list_runs(mailbox_id=mailbox_id)
    stages = {r["stage"] for r in runs}
    assert "email_fetch" in stages
    assert "classification" in stages
    assert "email_processing" in stages


def test_token_usage_recorded_from_structured_result(monkeypatch) -> None:
    mailbox_id, _ = _process_support_email(monkeypatch)
    runs = ObservabilityStore().list_runs(mailbox_id=mailbox_id)
    classification = next(r for r in runs if r["stage"] == "classification")
    assert classification["input_tokens"] == 100
    assert classification["output_tokens"] == 50
    assert classification["total_tokens"] == 150


def test_classification_metadata_recorded(monkeypatch) -> None:
    mailbox_id, _ = _process_support_email(monkeypatch)
    runs = ObservabilityStore().list_runs(mailbox_id=mailbox_id)
    classification = next(r for r in runs if r["stage"] == "classification")
    import json

    metadata = json.loads(classification["metadata_json"])
    assert "structured_valid" in metadata
    assert "topic_resolved" in metadata


def test_retrieval_metadata_recorded(monkeypatch) -> None:
    from email_assistant.core.knowledge_indexing import KnowledgeIndexService

    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com", "use_knowledge": True}
    ).json()["id"]
    client.post(
        f"/api/mailboxes/{mailbox_id}/topics",
        json={"name": "Refund", "description": "refunds"},
    )
    source = client.post(
        "/api/mailboxes/knowledge",
        json={"name": "Refund Policy", "content": "Refunds accepted within 30 days."},
    ).json()
    client.post(f"/api/mailboxes/{mailbox_id}/knowledge/{source['id']}")
    KnowledgeIndexService().index_source(mailbox_id, source)

    import email_assistant.core

    _mock_pipeline(monkeypatch)
    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: [
            {
                "sender": "a@x.com",
                "subject": "Refund",
                "body": "How long do I have to request a refund?",
                "timestamp": "2026-09-01T10:00:00Z",
                "mailbox_id": mid,
            }
        ],
    )
    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    email_id = client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0]["id"]
    client.post(f"/api/emails/{email_id}/process")

    runs = ObservabilityStore().list_runs(mailbox_id=mailbox_id)
    retrieval = next(r for r in runs if r["stage"] == "knowledge_retrieval")
    import json

    metadata = json.loads(retrieval["metadata_json"])
    assert metadata["returned_count"] >= 1
    assert metadata["embedding_model"] == "hashing"
    assert "stale_chunks_skipped" in metadata


def test_observer_best_effort_never_breaks_pipeline(monkeypatch) -> None:
    # If the observer store fails, processing still works.
    import email_assistant.core.observability as obs

    monkeypatch.setattr(
        obs.ObservabilityStore,
        "start_run",
        lambda self, data: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    mailbox_id, _ = _process_support_email(monkeypatch)
    # The email was still processed.
    assert client.get(f"/api/cases?mailbox_id={mailbox_id}").json()["count"] == 1
