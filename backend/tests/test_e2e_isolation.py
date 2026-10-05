"""P1 end-to-end isolation test.

Verifies the core design claim: each mailbox is an isolated business context
end-to-end — topics, knowledge, connectors, and processing runs never leak
across mailboxes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from email_assistant.core.knowledge_indexing import KnowledgeIndexService
from email_assistant.core.knowledge_retrieval import KnowledgeRetriever
from email_assistant.core.knowledge_store import KnowledgeStore
from email_assistant.core.observability import Observer

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.setenv("SQLITE_EMAIL_DB", str(tmp_path / "emails.db"))
    monkeypatch.setenv("KNOWLEDGE_DB", str(tmp_path / "knowledge.db"))
    monkeypatch.setenv("OBSERVABILITY_DB", str(tmp_path / "observability.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    store.clear()
    KnowledgeStore().clear()
    yield
    store.clear()
    KnowledgeStore().clear()


def _fake_kickoff(self, inputs=None, **kwargs):  # noqa: ANN001
    return SimpleNamespace(raw="Draft reply")


def _fake_classify(self, email_content, topics, fields=None):  # noqa: ANN001
    from email_assistant.core.structured_classification import (
        ClassificationOutcome,
    )

    return ClassificationOutcome(
        category="question",
        topic="refund",
        priority="normal",
        summary="refund request",
        custom_fields={},
        structured_valid=True,
        attempts=1,
    )


def test_full_pipeline_is_mailbox_isolated(monkeypatch) -> None:
    import crewai

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)
    from email_assistant.core.structured_classification import StructuredClassifier

    monkeypatch.setattr(StructuredClassifier, "classify", _fake_classify)

    # Build Support mailbox with refund topic + refund knowledge.
    support_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "support@x.com"}
    ).json()["id"]
    client.post(
        f"/api/mailboxes/{support_id}/topics",
        json={"name": "Refund", "description": "refund requests"},
    )
    support_source = client.post(
        "/api/mailboxes/knowledge",
        json={"name": "Refund Policy", "content": "Refund requests are accepted within 30 days."},
    ).json()
    client.post(f"/api/mailboxes/{support_id}/knowledge/{support_source['id']}")
    KnowledgeIndexService().index_source(support_id, support_source)

    # Build Sales mailbox with pricing topic + pricing knowledge.
    sales_id = client.post(
        "/api/mailboxes", json={"name": "Sales", "address": "sales@x.com"}
    ).json()["id"]
    client.post(
        f"/api/mailboxes/{sales_id}/topics",
        json={"name": "Pricing", "description": "pricing enquiries"},
    )
    sales_source = client.post(
        "/api/mailboxes/knowledge",
        json={"name": "Pricing Guide", "content": "Enterprise plans require a minimum of 100 seats."},
    ).json()
    client.post(f"/api/mailboxes/{sales_id}/knowledge/{sales_source['id']}")
    KnowledgeIndexService().index_source(sales_id, sales_source)

    # 1. Knowledge isolation: Support retrieval never returns Sales chunks.
    support_results = KnowledgeRetriever().search(support_id, "refund period")
    assert support_results
    sales_chunks = {c["content"] for c in KnowledgeStore().list_chunks(sales_id)}
    for r in support_results:
        assert r.content not in sales_chunks

    # 2. Topic isolation: Support topics do not include Sales topics.
    support_topics = client.get(f"/api/mailboxes/{support_id}/topics").json()
    support_topic_names = {t["name"] for t in support_topics}
    assert "Refund" in support_topic_names
    assert "Pricing" not in support_topic_names

    # 3. Ingest a Support email and process it.
    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: (
            [
                {
                    "sender": "cust@x.com",
                    "subject": "Refund question",
                    "body": "How long do I have to request a refund?",
                    "timestamp": "2026-09-01T10:00:00Z",
                    "mailbox_id": mid,
                }
            ]
            if mid == support_id
            else []
        ),
    )
    client.post("/api/emails/sync", json={"mailbox_id": support_id})
    email_id = client.get(f"/api/emails?mailbox_id={support_id}").json()["emails"][0]["id"]
    client.post(f"/api/emails/{email_id}/process")

    # 4. Case carries the Support mailbox_id + resolved topic.
    case = client.get(f"/api/cases?mailbox_id={support_id}").json()["cases"][0]
    assert case["mailbox_id"] == support_id
    assert case["topic_id"] is not None

    # 5. Sales sees nothing for the Support case.
    assert client.get(f"/api/cases?mailbox_id={sales_id}").json()["count"] == 0

    # 6. Processing runs are mailbox-scoped.
    runs = client.get(f"/api/mailboxes/{support_id}/processing-runs").json()
    assert any(r["stage"] == "email_processing" for r in runs)
    sales_runs = client.get(f"/api/mailboxes/{sales_id}/processing-runs").json()
    assert all(r["stage"] != "email_processing" for r in sales_runs)
