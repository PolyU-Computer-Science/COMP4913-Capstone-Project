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
    classification = SimpleNamespace(
        model_dump=lambda: {
            "category": "question",
            "topic": "refund",
            "priority": "normal",
            "summary": "s",
            "custom": {},
        }
    )
    usage = SimpleNamespace(
        get=lambda *a, **k: None,
    )
    return SimpleNamespace(
        pydantic=classification,
        raw="Draft",
        usage_metrics={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )


def _process_support_email(monkeypatch) -> tuple[int, str]:
    import crewai

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)

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
    assert "email_processing" in stages
    assert "field_extraction" in stages


def test_token_usage_recorded_from_crewai_result(monkeypatch) -> None:
    mailbox_id, _ = _process_support_email(monkeypatch)
    runs = ObservabilityStore().list_runs(mailbox_id=mailbox_id)
    processing = next(r for r in runs if r["stage"] == "email_processing")
    assert processing["input_tokens"] == 100
    assert processing["output_tokens"] == 50
    assert processing["total_tokens"] == 150


def test_field_extraction_metadata_recorded(monkeypatch) -> None:
    mailbox_id, _ = _process_support_email(monkeypatch)
    runs = ObservabilityStore().list_runs(mailbox_id=mailbox_id)
    extraction = next(r for r in runs if r["stage"] == "field_extraction")
    import json

    metadata = json.loads(extraction["metadata_json"])
    assert "fields_proposed" in metadata
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

    import crewai
    import email_assistant.core

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)
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
