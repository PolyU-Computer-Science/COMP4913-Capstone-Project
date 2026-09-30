"""Full E2E pipeline + failure injection tests (7C)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from email_assistant.core.knowledge_indexing import KnowledgeIndexService
from email_assistant.core.knowledge_store import KnowledgeStore
from email_assistant.core.observability_store import ObservabilityStore

client = TestClient(app)

SUPPORT_EMAIL = {
    "sender": "cust@example.com",
    "subject": "Refund question",
    "body": "How long do I have to request a refund?",
    "timestamp": "2026-09-01T10:00:00Z",
}

SALES_EMAIL = {
    "sender": "lead@example.com",
    "subject": "Enterprise pricing",
    "body": "What is the minimum number of seats?",
    "timestamp": "2026-09-01T11:00:00Z",
}


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.setenv("SQLITE_EMAIL_DB", str(tmp_path / "emails.db"))
    monkeypatch.setenv("KNOWLEDGE_DB", str(tmp_path / "knowledge.db"))
    monkeypatch.setenv("OBSERVABILITY_DB", str(tmp_path / "observability.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    store.clear()
    KnowledgeStore().clear()
    ObservabilityStore().clear()
    yield
    store.clear()
    KnowledgeStore().clear()


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
    return SimpleNamespace(pydantic=classification, raw="Draft reply")


def _seed_email(monkeypatch, mailbox_id, email):
    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: ([{**email, "mailbox_id": mid}] if mid == mailbox_id else []),
    )
    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})


def test_full_support_sales_pipeline_isolation(monkeypatch) -> None:
    import crewai

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)

    # Support mailbox.
    support_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "support@x.com"}
    ).json()["id"]
    client.post(
        f"/api/mailboxes/{support_id}/topics",
        json={"name": "Refund", "description": "refunds"},
    )
    support_source = client.post(
        "/api/mailboxes/knowledge",
        json={"name": "Refund Policy", "content": "Refunds accepted within 30 days."},
    ).json()
    client.post(f"/api/mailboxes/{support_id}/knowledge/{support_source['id']}")
    KnowledgeIndexService().index_source(support_id, support_source)

    # Sales mailbox.
    sales_id = client.post(
        "/api/mailboxes", json={"name": "Sales", "address": "sales@x.com"}
    ).json()["id"]
    client.post(
        f"/api/mailboxes/{sales_id}/topics",
        json={"name": "Pricing", "description": "pricing"},
    )
    sales_source = client.post(
        "/api/mailboxes/knowledge",
        json={"name": "Pricing Guide", "content": "Enterprise minimum 100 seats."},
    ).json()
    client.post(f"/api/mailboxes/{sales_id}/knowledge/{sales_source['id']}")
    KnowledgeIndexService().index_source(sales_id, sales_source)

    # Ingest + process a Support email.
    _seed_email(monkeypatch, support_id, SUPPORT_EMAIL)
    support_email_id = client.get(f"/api/emails?mailbox_id={support_id}").json()["emails"][0]["id"]
    client.post(f"/api/emails/{support_email_id}/process")

    case = client.get(f"/api/cases?mailbox_id={support_id}").json()["cases"][0]
    assert case["mailbox_id"] == support_id
    assert case["topic_id"] is not None

    # Sales has no such case.
    assert client.get(f"/api/cases?mailbox_id={sales_id}").json()["count"] == 0

    # Knowledge isolation.
    from email_assistant.core.knowledge_retrieval import KnowledgeRetriever

    support_results = KnowledgeRetriever().search(support_id, "refund period")
    sales_chunks = {c["content"] for c in KnowledgeStore().list_chunks(sales_id)}
    assert all(r.content not in sales_chunks for r in support_results)

    # Observability isolation: Sales has no Support processing run.
    support_runs = ObservabilityStore().list_runs(mailbox_id=support_id)
    sales_runs = ObservabilityStore().list_runs(mailbox_id=sales_id)
    assert any(r["stage"] == "email_processing" for r in support_runs)
    assert all(r["stage"] != "email_processing" for r in sales_runs)


def test_imap_failure_returns_502(monkeypatch) -> None:
    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mb_id=None: (_ for _ in ()).throw(RuntimeError("IMAP down")),
    )
    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    response = client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    assert response.status_code == 502


def test_classifier_failure_marks_email_failed(monkeypatch) -> None:
    import crewai
    import email_assistant.core

    monkeypatch.setattr(
        crewai.Crew,
        "kickoff",
        lambda self, inputs=None, **kwargs: (_ for _ in ()).throw(RuntimeError("LLM timeout")),
    )
    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: [{**SUPPORT_EMAIL, "mailbox_id": mid}],
    )
    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    email_id = client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0]["id"]

    # The endpoint re-raises; use a non-raising client to observe the 500 and
    # verify the email was marked failed.
    from fastapi.testclient import TestClient as TC

    plain = TC(app, raise_server_exceptions=False)
    response = plain.post(f"/api/emails/{email_id}/process")
    assert response.status_code == 500

    email = client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0]
    assert email["status"] == "failed"


def test_smtp_failure_does_not_mark_sent(monkeypatch) -> None:
    import crewai
    import email_assistant.core
    import email_assistant.core.email_sender as sender_module

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)
    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: [{**SUPPORT_EMAIL, "mailbox_id": mid}],
    )

    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    email_id = client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0]["id"]
    client.post(f"/api/emails/{email_id}/process")

    monkeypatch.setattr(
        sender_module,
        "send_reply",
        lambda account, to, subject, body: (_ for _ in ()).throw(RuntimeError("SMTP down")),
    )
    import email_assistant.core.settings_store as settings_module

    monkeypatch.setattr(
        settings_module.SettingsStore,
        "get_enabled_mail_account",
        lambda self: {"address": "s@x.com", "smtp_host": "smtp", "smtp_port": 587, "password": "pw"},
    )

    response = client.post(f"/api/cases/{email_id}/send")
    assert response.status_code == 502

    # Case must NOT be marked sent.
    case = client.get(f"/api/cases?mailbox_id={mailbox_id}").json()["cases"][0]
    assert case["sent_at"] is None


def test_manual_field_not_overwritten_by_processing(monkeypatch) -> None:
    import crewai
    import email_assistant.core

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)
    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: [{**SUPPORT_EMAIL, "mailbox_id": mid}],
    )

    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    field = client.post(
        f"/api/mailboxes/{mailbox_id}/fields",
        json={"name": "order_id", "type": "text"},
    ).json()
    field_id = field["id"]

    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    email_id = client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0]["id"]
    client.post(f"/api/emails/{email_id}/process")

    # Manually set order_id.
    client.put(
        f"/api/cases/{email_id}/fields",
        json={"values": {str(field_id): "MANUAL-1"}},
    )

    # Reprocess — manual value must remain.
    client.post(f"/api/emails/{email_id}/process")
    fields = client.get(f"/api/cases/{email_id}/fields").json()
    assert fields[0]["value"] == "MANUAL-1"
