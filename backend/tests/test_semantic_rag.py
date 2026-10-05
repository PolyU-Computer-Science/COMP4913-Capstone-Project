"""Phase 4 — production semantic RAG tests (all offline, mocked HTTP)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store
from email_assistant.core.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingDimensionMismatch,
    get_embedding_client,
)
from email_assistant.core.knowledge_indexing import KnowledgeIndexService
from email_assistant.core.knowledge_retrieval import KnowledgeRetriever, RetrievalStats
from email_assistant.core.knowledge_store import KnowledgeStore
from email_assistant.core.openai_embeddings import (
    OpenAICompatibleEmbeddingClient,
)

client = TestClient(app)


class _FakeTransport:
    def __init__(self, dim: int = 8):
        self.dim = dim
        self.calls = 0

    def post(self, url, json):
        self.calls += 1
        inputs = json["input"]
        return _FakeResponse(
            200,
            {
                "data": [
                    {
                        "index": i,
                        "embedding": [float((hash(t) + i + j) % self.dim) for j in range(self.dim)],
                    }
                    for i, t in enumerate(inputs)
                ]
            },
        )


class _FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data
        self.text = ""

    def json(self):
        return self._json


def _embedding_client(dim: int = 8) -> OpenAICompatibleEmbeddingClient:
    return OpenAICompatibleEmbeddingClient(
        api_key="test",
        model="qwen/qwen3-embedding-8b",
        transport=_FakeTransport(dim),
        provider="openrouter",
    )


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


# ---- explicit fallback ----

def test_openrouter_missing_key_raises_config_error(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(EmbeddingConfigurationError):
        get_embedding_client("openrouter")


def test_unknown_provider_raises(monkeypatch) -> None:
    with pytest.raises(EmbeddingConfigurationError):
        get_embedding_client("bogus-provider")


# ---- indexing with semantic client ----

def _make_mailbox_with_index(name: str, content: str, embedding_client) -> int:
    mailbox_id = client.post(
        "/api/mailboxes", json={"name": name, "address": f"{name.lower()}@x.com"}
    ).json()["id"]
    source = client.post(
        "/api/mailboxes/knowledge", json={"name": f"{name} KB", "content": content}
    ).json()
    client.post(f"/api/mailboxes/{mailbox_id}/knowledge/{source['id']}")
    KnowledgeIndexService(embedding_client=embedding_client).index_source(mailbox_id, source)
    return mailbox_id


def test_semantic_index_persists_identity() -> None:
    client = _embedding_client(dim=12)
    mailbox_id = _make_mailbox_with_index("Support", "Refunds accepted within 30 days.", client)

    docs = KnowledgeStore().list_documents(mailbox_id)
    assert docs[0]["embedding_provider"] == "openrouter"
    assert docs[0]["embedding_model"] == "qwen/qwen3-embedding-8b"
    assert docs[0]["embedding_dim"] == 12

    chunks = KnowledgeStore().list_chunks(mailbox_id)
    assert all(c["embedding_dim"] == 12 for c in chunks)


def test_semantic_retrieval_uses_identity() -> None:
    client = _embedding_client(dim=12)
    mailbox_id = _make_mailbox_with_index("Support", "Refunds accepted within 30 days.", client)

    retriever = KnowledgeRetriever(embedding_client=client)
    results, stats = retriever.search_detailed(mailbox_id, "refund period")
    assert len(results) >= 1
    assert stats.returned_count >= 1
    assert stats.latency_ms >= 0
    assert stats.source_count >= 1
    assert stats.max_score > 0


def test_retrieval_stats_reflect_stale_skipped() -> None:
    # Index with hashing dim 256, retrieve with openrouter dim 8 -> all stale.
    hashing_client = None  # will use default hashing
    mailbox_id = _make_mailbox_with_index(
        "Support", "Refunds accepted within 30 days.", hashing_client
    )
    openrouter = _embedding_client(dim=8)
    retriever = KnowledgeRetriever(embedding_client=openrouter)
    results, stats = retriever.search_detailed(mailbox_id, "refund")
    assert results == []
    assert stats.stale_chunks_skipped >= 1
    assert stats.returned_count == 0


# ---- retrieval isolation ----

def test_support_never_retrieves_sales_knowledge() -> None:
    client = _embedding_client(dim=8)
    support_id = _make_mailbox_with_index(
        "Support", "Refund requests accepted within 30 days.", client
    )
    sales_id = _make_mailbox_with_index(
        "Sales", "Enterprise plans require 100 seats minimum.", client
    )

    retriever = KnowledgeRetriever(embedding_client=client)
    support_results = retriever.search(support_id, "refund period")
    sales_chunks = {c["content"] for c in KnowledgeStore().list_chunks(sales_id)}
    assert support_results
    assert all(r.content not in sales_chunks for r in support_results)


# ---- search API exposes identity + stats ----

def test_search_api_exposes_identity_and_stats() -> None:
    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    source = client.post(
        "/api/mailboxes/knowledge",
        json={"name": "Refund Policy", "content": "Refunds accepted within 30 days."},
    ).json()
    client.post(f"/api/mailboxes/{mailbox_id}/knowledge/{source['id']}")
    # Index with hashing (default client used by index service).
    KnowledgeIndexService().index_source(mailbox_id, source)

    response = client.post(
        f"/api/mailboxes/{mailbox_id}/knowledge/search",
        json={"query": "refund", "top_k": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["embedding"]["model"] == "hashing"
    assert body["stats"]["returned_count"] >= 1
    assert "latency_ms" in body["stats"]
    assert "chunks_considered" in body["stats"]
    assert len(body["results"]) >= 1


# ---- draft provenance ----

def test_draft_stores_knowledge_provenance(monkeypatch) -> None:
    import crewai
    import email_assistant.core

    monkeypatch.setattr(
        crewai.Crew,
        "kickoff",
        lambda self, inputs=None, **kwargs: SimpleNamespace(raw="Draft reply"),
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
            structured_valid=True,
            attempts=1,
        ),
    )

    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com", "use_knowledge": True}
    ).json()["id"]
    source = client.post(
        "/api/mailboxes/knowledge",
        json={"name": "Refund Policy", "content": "Refunds accepted within 30 days."},
    ).json()
    client.post(f"/api/mailboxes/{mailbox_id}/knowledge/{source['id']}")
    KnowledgeIndexService().index_source(mailbox_id, source)

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

    case = client.get(f"/api/cases?mailbox_id={mailbox_id}").json()["cases"][0]
    assert len(case["knowledge_refs"]) >= 1
    assert "source_id" in case["knowledge_refs"][0]
    assert "chunk_id" in case["knowledge_refs"][0]


def test_no_rag_empty_retrieval_still_drafts(monkeypatch) -> None:
    import crewai
    import email_assistant.core

    monkeypatch.setattr(
        crewai.Crew,
        "kickoff",
        lambda self, inputs=None, **kwargs: SimpleNamespace(raw="Draft reply"),
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
            structured_valid=True,
            attempts=1,
        ),
    )

    # No knowledge configured at all.
    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
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
    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})
    email_id = client.get(f"/api/emails?mailbox_id={mailbox_id}").json()["emails"][0]["id"]
    response = client.post(f"/api/emails/{email_id}/process")
    assert response.status_code == 200

    case = client.get(f"/api/cases?mailbox_id={mailbox_id}").json()["cases"][0]
    assert case["knowledge_refs"] == []
