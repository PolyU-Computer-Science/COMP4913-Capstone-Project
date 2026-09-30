"""Cross-mailbox isolation tests.

These verify the core design claim that each mailbox is an isolated business
context: emails, cases, stats and pending queues are scoped to a mailbox, and
a Support email can never appear in a Sales query.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store

client = TestClient(app)

SUPPORT_EMAIL = {
    "sender": "sarah@example.com",
    "subject": "Password reset",
    "body": "I cannot log in.",
    "timestamp": "2026-09-01T10:00:00Z",
}

SALES_EMAIL = {
    "sender": "jane@example.com",
    "subject": "Enterprise pricing",
    "body": "How much is the enterprise plan?",
    "timestamp": "2026-09-02T10:00:00Z",
}


def _fake_kickoff(self, inputs=None, **kwargs):  # noqa: ANN001
    classification = SimpleNamespace(
        model_dump=lambda: {
            "category": "question",
            "topic": "topic",
            "priority": "normal",
            "summary": "summary",
            "custom": {},
        }
    )
    return SimpleNamespace(pydantic=classification, raw="Draft")


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.setenv("SQLITE_EMAIL_DB", str(tmp_path / "emails.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    store.clear()
    yield
    store.clear()


def _create_mailbox(name: str, address: str) -> int:
    return client.post(
        "/api/mailboxes", json={"name": name, "address": address}
    ).json()["id"]


def _seed_email(monkeypatch, mailbox_id: int, email: dict) -> None:
    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: ([{**email, "mailbox_id": mid}] if mid == mailbox_id else []),
    )
    client.post("/api/emails/sync", json={"mailbox_id": mailbox_id})


def test_email_scope_is_isolated_per_mailbox(monkeypatch) -> None:
    support_id = _create_mailbox("Support", "support@company.com")
    sales_id = _create_mailbox("Sales", "sales@company.com")

    import email_assistant.core

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: (
            [{**SUPPORT_EMAIL, "mailbox_id": mid}] if mid == support_id else []
        ),
    )
    client.post("/api/emails/sync", json={"mailbox_id": support_id})

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: (
            [{**SALES_EMAIL, "mailbox_id": mid}] if mid == sales_id else []
        ),
    )
    client.post("/api/emails/sync", json={"mailbox_id": sales_id})

    # All mailboxes -> 2 emails.
    assert client.get("/api/emails").json()["count"] == 2

    # Support scope -> only Support email.
    support = client.get(f"/api/emails?mailbox_id={support_id}").json()
    assert support["count"] == 1
    assert support["emails"][0]["subject"] == "Password reset"
    assert support["emails"][0]["mailbox_id"] == support_id

    # Sales scope -> only Sales email.
    sales = client.get(f"/api/emails?mailbox_id={sales_id}").json()
    assert sales["count"] == 1
    assert sales["emails"][0]["subject"] == "Enterprise pricing"
    assert sales["emails"][0]["mailbox_id"] == sales_id


def test_cases_are_isolated_per_mailbox(monkeypatch) -> None:
    import crewai

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)

    support_id = _create_mailbox("Support", "support@company.com")
    sales_id = _create_mailbox("Sales", "sales@company.com")

    _seed_email(monkeypatch, support_id, SUPPORT_EMAIL)
    _seed_email(monkeypatch, sales_id, SALES_EMAIL)

    support_email_ids = client.get(
        f"/api/emails?mailbox_id={support_id}"
    ).json()["emails"]
    sales_email_ids = client.get(f"/api/emails?mailbox_id={sales_id}").json()[
        "emails"
    ]

    for email in support_email_ids + sales_email_ids:
        client.post(f"/api/emails/{email['id']}/process")

    support_cases = client.get(f"/api/cases?mailbox_id={support_id}").json()
    assert support_cases["count"] == 1
    assert support_cases["cases"][0]["email"]["subject"] == "Password reset"
    assert support_cases["cases"][0]["mailbox_id"] == support_id

    sales_cases = client.get(f"/api/cases?mailbox_id={sales_id}").json()
    assert sales_cases["count"] == 1
    assert sales_cases["cases"][0]["email"]["subject"] == "Enterprise pricing"
    assert sales_cases["cases"][0]["mailbox_id"] == sales_id


def test_stats_are_isolated_per_mailbox(monkeypatch) -> None:
    import crewai

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)

    support_id = _create_mailbox("Support", "support@company.com")
    sales_id = _create_mailbox("Sales", "sales@company.com")

    _seed_email(monkeypatch, support_id, SUPPORT_EMAIL)
    _seed_email(monkeypatch, sales_id, SALES_EMAIL)

    email_ids = client.get("/api/emails").json()["emails"]
    for email in email_ids:
        client.post(f"/api/emails/{email['id']}/process")

    support_stats = client.get(f"/api/stats?mailbox_id={support_id}").json()
    sales_stats = client.get(f"/api/stats?mailbox_id={sales_id}").json()

    assert support_stats["processed"] == 1
    assert support_stats["total_emails"] == 1
    assert sales_stats["processed"] == 1
    assert sales_stats["total_emails"] == 1

    all_stats = client.get("/api/stats").json()
    assert all_stats["total_emails"] == 2
    assert all_stats["processed"] == 2


def test_process_all_is_scoped_to_mailbox(monkeypatch) -> None:
    import crewai

    monkeypatch.setattr(crewai.Crew, "kickoff", _fake_kickoff)

    support_id = _create_mailbox("Support", "support@company.com")
    sales_id = _create_mailbox("Sales", "sales@company.com")

    _seed_email(monkeypatch, support_id, SUPPORT_EMAIL)
    _seed_email(monkeypatch, sales_id, SALES_EMAIL)

    # Process only the Sales mailbox.
    result = client.post(f"/api/emails/process-all?mailbox_id={sales_id}").json()
    assert result["queued"] == 1
    assert result["processed"] == 1

    # Support email must remain unprocessed.
    support_emails = client.get(
        f"/api/emails?mailbox_id={support_id}"
    ).json()["emails"]
    assert support_emails[0]["status"] == "new"

    sales_emails = client.get(f"/api/emails?mailbox_id={sales_id}").json()["emails"]
    assert sales_emails[0]["status"] == "processed"


def test_legacy_backfill_migrates_null_mailbox_emails(monkeypatch) -> None:
    from email_assistant.core.migrations import migrate_legacy_emails

    # Seed via the store without mailbox_id — writes a NULL mailbox_id row
    # (simulating pre-mailbox-scoping data).
    store.sync_emails([dict(SUPPORT_EMAIL)])

    migrated = migrate_legacy_emails()
    assert migrated == 1

    emails = client.get("/api/emails").json()["emails"]
    assert emails[0]["mailbox_id"] is not None

    # A second run is a no-op.
    assert migrate_legacy_emails() == 0


def test_legacy_mailbox_is_system_and_hidden(monkeypatch) -> None:
    import email_assistant.core
    from email_assistant.core.migrations import migrate_legacy_emails

    store.sync_emails([dict(SUPPORT_EMAIL)])
    migrate_legacy_emails()

    # A real mailbox is visible; the Legacy system mailbox is hidden by default.
    client.post(
        "/api/mailboxes", json={"name": "Support", "address": "s@x.com"}
    )
    listed = client.get("/api/mailboxes").json()
    names = {m["name"] for m in listed}
    assert "Support" in names
    assert "Legacy" not in names

    # Explicitly requesting system mailboxes reveals Legacy with is_system.
    with_system = client.get("/api/mailboxes?include_system=true").json()
    legacy = next(m for m in with_system if m["name"] == "Legacy")
    assert legacy["is_system"] is True


def test_dedup_is_scoped_to_mailbox(monkeypatch) -> None:
    import email_assistant.core

    support_id = _create_mailbox("Support", "support@company.com")
    sales_id = _create_mailbox("Sales", "sales@company.com")

    # Same message delivered to both mailboxes.
    shared_email = {
        "sender": "same@example.com",
        "subject": "Shared thread",
        "body": "hello",
        "timestamp": "2026-09-03T10:00:00Z",
    }

    monkeypatch.setattr(
        email_assistant.core,
        "fetch_emails",
        lambda mid: [{**shared_email, "mailbox_id": mid}],
    )
    client.post("/api/emails/sync", json={"mailbox_id": support_id})
    client.post("/api/emails/sync", json={"mailbox_id": sales_id})

    # Two distinct tickets, one per mailbox.
    assert client.get("/api/emails").json()["count"] == 2
    assert client.get(f"/api/emails?mailbox_id={support_id}").json()["count"] == 1
    assert client.get(f"/api/emails?mailbox_id={sales_id}").json()["count"] == 1
