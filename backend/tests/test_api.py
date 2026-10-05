"""API integration tests using FastAPI TestClient (no LLM network calls)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store

client = TestClient(app)

SAMPLE_EMAIL = {
    "sender": "sarah.chen@example.com",
    "subject": "Meeting Request",
    "body": "Hi team, can we schedule a meeting?",
    "timestamp": "2026-07-28T14:30:00Z",
}


def _fake_kickoff(self, inputs=None, **kwargs):  # noqa: ANN001
    classification = SimpleNamespace(
        model_dump=lambda: {
            "category": "question",
            "topic": "meeting",
            "priority": "normal",
            "urgency_score": 3,
            "summary": "A meeting request",
            "custom": {},
        }
    )
    return SimpleNamespace(pydantic=classification, raw="Draft reply text")


def _fake_structured_generate(
    self, *, system, user, response_model
):  # noqa: ANN001
    data = response_model(
        category="question",
        topic="meeting",
        priority="normal",
        summary="A meeting request",
        custom_fields={},
    )
    from email_assistant.core.structured_llm import StructuredLLMResult

    return StructuredLLMResult(
        data=data,
        raw='{"category": "question"}',
        valid=True,
        attempts=1,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )


def _mock_ai_pipeline(monkeypatch: pytest.MonkeyPatch, draft: str = "Draft reply text") -> None:
    """Mock both classification (structured runtime) and drafting (crew).

    Also stubs the structured client factory so no test can reach a real
    LLM endpoint even if the classify mock is replaced.
    """
    import crewai
    import email_assistant.core.structured_llm as structured_llm_module
    from email_assistant.core.structured_classification import (
        StructuredClassifier,
    )

    monkeypatch.setattr(
        structured_llm_module,
        "build_structured_client_from_settings",
        lambda settings: object(),
    )

    def fake_classify(self, email_content, topics, fields=None):  # noqa: ANN001
        from email_assistant.core.structured_classification import (
            ClassificationOutcome,
        )

        return ClassificationOutcome(
            category="question",
            topic="meeting",
            topic_id=None,
            topic_resolved=False,
            priority="normal",
            summary="A meeting request",
            custom_fields={},
            structured_valid=True,
            attempts=1,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )

    monkeypatch.setattr(StructuredClassifier, "classify", fake_classify)
    monkeypatch.setattr(
        crewai.Crew,
        "kickoff",
        lambda self, inputs=None, **kwargs: SimpleNamespace(
            raw=draft, tasks_output=[]
        ),
    )


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    store.clear()
    yield
    store.clear()


def _sync_sample(monkeypatch: pytest.MonkeyPatch, mailbox_id: int = 1) -> list[str]:
    """Create a mailbox, sync one sample email into it, return the id."""
    import email_assistant.core

    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mb_id=None: [SAMPLE_EMAIL] if mb_id == mailbox_id else [],
    )
    response = client.post(
        "/api/emails/sync", json={"mailbox_id": mailbox_id}
    )
    assert response.status_code == 200
    return [email["id"] for email in response.json()["emails"]]


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sync_emails_persists_and_dedupes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _sync_sample(monkeypatch)
    assert len(ids) == 1
    assert ids[0]

    first = client.get("/api/emails").json()
    assert first["count"] == 1
    assert first["emails"][0]["sender"] == "sarah.chen@example.com"

    # Syncing again must not duplicate.
    response = client.post("/api/emails/sync")
    assert response.status_code == 200
    assert response.json()["synced"] == 0
    assert response.json()["count"] == 1


def test_list_emails_is_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _sync_sample(monkeypatch)

    import email_assistant.core

    called = {"n": 0}
    original = email_assistant.core.fetch_emails

    def counting_fetch():
        called["n"] += 1
        return original()

    monkeypatch.setattr(email_assistant.core, "fetch_emails", counting_fetch)

    response = client.get("/api/emails")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert called["n"] == 0


def test_process_email_returns_case(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_ai_pipeline(monkeypatch)
    email_id = _sync_sample(monkeypatch)[0]

    response = client.post(f"/api/emails/{email_id}/process")

    assert response.status_code == 200
    body = response.json()
    assert body["case"]["id"] == email_id
    assert body["case"]["classification"]["category"] == "question"
    assert body["case"]["draft"] == "Draft reply text"


def test_process_missing_email_returns_404() -> None:
    response = client.post("/api/emails/does-not-exist/process")
    assert response.status_code == 404


def test_process_all_processes_pending_emails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_ai_pipeline(monkeypatch)
    _sync_sample(monkeypatch)
    # Add a second pending email.
    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mb_id=None: [
            {
                "sender": "bob@example.com",
                "subject": "Second email",
                "body": "Another question",
                "timestamp": "2026-07-29T10:00:00Z",
            }
        ] if mb_id else [],
    )
    client.post("/api/emails/sync")

    response = client.post("/api/emails/process-all")
    assert response.status_code == 200
    body = response.json()
    assert body["queued"] == 2
    assert body["processed"] == 2
    assert body["failed"] == []

    emails = client.get("/api/emails").json()["emails"]
    assert all(email["status"] == "processed" for email in emails)

    # A second run is a no-op (nothing pending).
    again = client.post("/api/emails/process-all").json()
    assert again["queued"] == 0
    assert again["processed"] == 0


def test_process_all_continues_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_ai_pipeline(monkeypatch)
    _sync_sample(monkeypatch)
    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mb_id=None: [
            {
                "sender": "bob@example.com",
                "subject": "Second email",
                "body": "Another question",
                "timestamp": "2026-07-29T10:00:00Z",
            }
        ] if mb_id else [],
    )
    client.post("/api/emails/sync")

    import crewai

    calls = {"n": 0}
    from email_assistant.core.structured_classification import (
        ClassificationOutcome,
        StructuredClassifier,
    )

    def flaky_kickoff(self, inputs=None, **kwargs):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("LLM down")
        return SimpleNamespace(raw="Draft reply text", tasks_output=[])

    monkeypatch.setattr(crewai.Crew, "kickoff", flaky_kickoff)

    def flaky_classify(self, email_content, topics, fields=None):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("LLM down")
        return ClassificationOutcome(
            category="question",
            topic="meeting",
            priority="normal",
            summary="A meeting request",
            structured_valid=True,
            attempts=1,
        )

    monkeypatch.setattr(StructuredClassifier, "classify", flaky_classify)

    body = client.post("/api/emails/process-all").json()
    assert body["queued"] == 2
    assert body["processed"] == 1
    assert len(body["failed"]) == 1

    emails = client.get("/api/emails").json()["emails"]
    statuses = {email["id"]: email["status"] for email in emails}
    # The failed email persists as 'failed' (retryable from the UI).
    assert sorted(statuses.values()) == ["failed", "processed"]


def test_cases_and_stats_reflect_processed_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_ai_pipeline(monkeypatch)
    email_id = _sync_sample(monkeypatch)[0]

    client.post(f"/api/emails/{email_id}/process")

    cases = client.get("/api/cases")
    assert cases.status_code == 200
    assert cases.json()["count"] == 1
    assert cases.json()["cases"][0]["classification"]["category"] == "question"

    stats = client.get("/api/stats")
    assert stats.status_code == 200
    body = stats.json()
    assert body["processed"] == 1
    assert body["category_distribution"][0]["name"] == "Question"
    assert body["recent_activity"][0]["email"] == "Meeting Request"


def test_stats_empty_store() -> None:
    stats = client.get("/api/stats")
    assert stats.status_code == 200
    body = stats.json()
    assert body["total_emails"] == 0
    assert body["processed"] == 0
    assert body["pending"] == 0
    assert body["success_rate"] == 0.0
    assert body["category_distribution"] == []


def test_get_attachment_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    import email_assistant.core

    mailbox_id = client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    ).json()["id"]
    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mb_id=None: [
            {
                "sender": "sarah.chen@example.com",
                "subject": "With image",
                "body": "text",
                "html": '<img src="cid:logo">',
                "timestamp": "2026-07-28T14:30:00Z",
                "attachments": [
                    {
                        "cid": "logo",
                        "content_type": "image/png",
                        "filename": "logo.png",
                        "data": b"\x89PNG",
                    }
                ],
            }
        ],
    )

    response = client.post(
        "/api/emails/sync", json={"mailbox_id": mailbox_id}
    )
    assert response.status_code == 200
    email_id = response.json()["emails"][0]["id"]
    assert response.json()["emails"][0]["html"] == '<img src="cid:logo">'

    image = client.get(f"/api/emails/{email_id}/attachments/logo")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == b"\x89PNG"

    missing = client.get(f"/api/emails/{email_id}/attachments/nope")
    assert missing.status_code == 404


def test_process_returns_422_when_classification_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import crewai
    from email_assistant.core.structured_classification import StructuredClassifier

    def failing_classify(self, email_content, topics, fields=None):  # noqa: ANN001
        from email_assistant.core.structured_classification import (
            ClassificationOutcome,
        )

        return ClassificationOutcome(category="", error="no valid output")

    monkeypatch.setattr(StructuredClassifier, "classify", failing_classify)
    email_id = _sync_sample(monkeypatch)[0]

    response = client.post(f"/api/emails/{email_id}/process")
    assert response.status_code == 422

    # No garbage case should be persisted.
    assert client.get("/api/cases").json()["count"] == 0


def test_process_recovers_python_literal_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from email_assistant.core.structured_classification import (
        ClassificationOutcome,
        StructuredClassifier,
    )

    def fallback_classify(self, email_content, topics, fields=None):  # noqa: ANN001
        return ClassificationOutcome(
            category="spam",
            topic="phishing_alert",
            priority="low",
            summary="A suspicious email",
            structured_valid=False,
            fallback_parser_used=True,
            attempts=2,
        )

    monkeypatch.setattr(StructuredClassifier, "classify", fallback_classify)
    import crewai

    monkeypatch.setattr(
        crewai.Crew,
        "kickoff",
        lambda self, inputs=None, **kwargs: SimpleNamespace(
            raw="Draft reply text", tasks_output=[]
        ),
    )
    email_id = _sync_sample(monkeypatch)[0]

    response = client.post(f"/api/emails/{email_id}/process")
    assert response.status_code == 200
    body = response.json()
    assert body["case"]["classification"]["category"] == "spam"
    assert body["case"]["classification"]["topic"] == "phishing_alert"
    assert body["case"]["draft"] == "Draft reply text"


def test_update_case_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_ai_pipeline(monkeypatch)
    email_id = _sync_sample(monkeypatch)[0]
    client.post(f"/api/emails/{email_id}/process")

    response = client.patch(
        f"/api/cases/{email_id}", json={"draft": "Edited draft"}
    )
    assert response.status_code == 200
    assert response.json()["draft"] == "Edited draft"

    missing = client.patch("/api/cases/nope", json={"draft": "x"})
    assert missing.status_code == 404


def test_send_case(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_ai_pipeline(monkeypatch)
    email_id = _sync_sample(monkeypatch)[0]
    client.post(f"/api/emails/{email_id}/process")

    sent_calls: list[dict] = []
    import email_assistant.core.email_sender as sender_module

    monkeypatch.setattr(
        sender_module,
        "send_reply",
        lambda account, to, subject, body: sent_calls.append(
            {"account": account, "to": to, "subject": subject, "body": body}
        ),
    )
    # Give the case's own mailbox an SMTP config (used for sending).
    mailbox_id = client.get("/api/mailboxes").json()[0]["id"]
    client.put(
        f"/api/mailboxes/{mailbox_id}",
        json={"name": "Support", "address": "s@x.com", "smtp_host": "smtp.s-x.com", "smtp_port": 587},
    )
    from email_assistant.core.settings_store import SettingsStore

    SettingsStore().set_mailbox_password(mailbox_id, "pw")

    response = client.post(f"/api/cases/{email_id}/send")
    assert response.status_code == 200
    body = response.json()
    assert body["sent_at"]
    assert body["email"]["status"] == "sent"

    assert len(sent_calls) == 1
    assert sent_calls[0]["to"] == "sarah.chen@example.com"
    assert sent_calls[0]["subject"] == "Meeting Request"
    # Sent from the case's own mailbox, not a global account.
    assert sent_calls[0]["account"]["address"] == "s@x.com"


def test_send_case_uses_own_mailbox_not_global(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-mailbox isolation: a case must be sent from its own mailbox."""
    _mock_ai_pipeline(monkeypatch)
    email_id = _sync_sample(monkeypatch)[0]
    client.post(f"/api/emails/{email_id}/process")

    # A different mailbox is globally "enabled" — it must NOT be used.
    import email_assistant.core.email_sender as sender_module

    sent_calls: list[dict] = []
    monkeypatch.setattr(
        sender_module,
        "send_reply",
        lambda account, to, subject, body: sent_calls.append({"account": account}),
    )
    # Configure SMTP on the case's own mailbox.
    mailbox_id = client.get("/api/mailboxes").json()[0]["id"]
    client.put(
        f"/api/mailboxes/{mailbox_id}",
        json={"name": "Support", "address": "s@x.com", "smtp_host": "smtp.s-x.com", "smtp_port": 587},
    )
    from email_assistant.core.settings_store import SettingsStore

    SettingsStore().set_mailbox_password(mailbox_id, "pw")

    # A different mailbox also has SMTP configured — it must NOT be used.
    client.post(
        "/api/mailboxes",
        json={
            "name": "Sales",
            "address": "sales@x.com",
            "smtp_host": "smtp.sales-x.com",
            "smtp_port": 587,
        },
    )
    sales_id = client.get("/api/mailboxes").json()[-1]["id"]
    SettingsStore().set_mailbox_password(sales_id, "pw")

    response = client.post(f"/api/cases/{email_id}/send")
    assert response.status_code == 200
    assert sent_calls[0]["account"]["address"] == "s@x.com"


def test_send_case_requires_mailbox_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_ai_pipeline(monkeypatch)
    email_id = _sync_sample(monkeypatch)[0]
    client.post(f"/api/emails/{email_id}/process")

    # The case's mailbox has no SMTP host configured.
    response = client.post(f"/api/cases/{email_id}/send")
    assert response.status_code == 400
