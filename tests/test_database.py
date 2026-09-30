from __future__ import annotations

from email_assistant.core.database import Database, make_email_id

EMAIL = {
    "sender": "sarah.chen@example.com",
    "subject": "Meeting Request",
    "body": "Hi team, can we schedule a meeting?",
    "timestamp": "2026-07-28T14:30:00Z",
}

CLASSIFICATION = {
    "category": "question",
    "topic": "meeting",
    "priority": "normal",
    "summary": "A meeting request",
    "custom": {"product": "app"},
}


def test_make_email_id_is_stable() -> None:
    assert make_email_id("a", "b", "c") == make_email_id("a", "b", "c")
    assert make_email_id("a", "b", "c") != make_email_id("a", "b", "d")


def test_upsert_dedupes(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    assert db.upsert_email(EMAIL) is True
    assert db.upsert_email(EMAIL) is False
    assert len(db.list_emails()) == 1


def test_persists_across_instances(tmp_path) -> None:
    path = str(tmp_path / "emails.db")
    first = Database(path)
    first.upsert_email(EMAIL)

    second = Database(path)
    emails = second.list_emails()
    assert len(emails) == 1
    assert emails[0]["sender"] == "sarah.chen@example.com"


def test_save_processing_and_list_cases(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    email_id = make_email_id(
        EMAIL["sender"], EMAIL["subject"], EMAIL["timestamp"]
    )
    db.upsert_email(EMAIL)

    case = db.save_processing(email_id, CLASSIFICATION, "Draft reply text")
    assert case is not None
    assert case["classification"]["category"] == "question"
    assert case["classification"]["custom"] == {"product": "app"}
    assert case["draft"] == "Draft reply text"
    assert case["created_at"]

    cases = db.list_cases()
    assert len(cases) == 1
    assert cases[0]["email"]["subject"] == "Meeting Request"


def test_save_processing_unknown_id_returns_none(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    assert db.save_processing("nope", CLASSIFICATION, "draft") is None


def test_clear_removes_rows(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    db.upsert_email(EMAIL)
    db.clear()
    assert db.list_emails() == []


def test_html_and_attachment_persist(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    email = {
        **EMAIL,
        "html": '<html><body><img src="cid:logo"></body></html>',
        "attachments": [
            {
                "cid": "logo",
                "content_type": "image/png",
                "filename": "logo.png",
                "data": b"\x89PNG",
            }
        ],
    }
    assert db.upsert_email(email) is True

    emails = db.list_emails()
    assert emails[0]["html"] == email["html"]

    email_id = emails[0]["id"]
    attachment = db.get_attachment(email_id, "logo")
    assert attachment is not None
    content_type, data = attachment
    assert content_type == "image/png"
    assert data == b"\x89PNG"


def test_get_attachment_unknown_returns_none(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    db.upsert_email(EMAIL)
    assert db.get_attachment("nope", "logo") is None


def test_upsert_dedupes_attachments(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    email = {
        **EMAIL,
        "attachments": [
            {"cid": "logo", "content_type": "image/png", "filename": "", "data": b"x"}
        ],
    }
    assert db.upsert_email(email) is True
    assert db.upsert_email(email) is False

    email_id = db.list_emails()[0]["id"]
    assert db.get_attachment(email_id, "logo") is not None


def test_save_draft_and_mark_sent(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    email_id = make_email_id(
        EMAIL["sender"], EMAIL["subject"], EMAIL["timestamp"]
    )
    db.upsert_email(EMAIL)
    db.save_processing(email_id, CLASSIFICATION, "Draft v1")

    case = db.get_case(email_id)
    assert case is not None
    assert case["draft"] == "Draft v1"
    assert case["sent_at"] is None

    updated = db.save_draft(email_id, "Draft v2")
    assert updated is not None
    assert updated["draft"] == "Draft v2"

    sent = db.mark_sent(email_id)
    assert sent is not None
    assert sent["sent_at"]
    assert sent["email"]["status"] == "sent"


def test_reprocess_clears_sent_at(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    email_id = make_email_id(
        EMAIL["sender"], EMAIL["subject"], EMAIL["timestamp"]
    )
    db.upsert_email(EMAIL)
    db.save_processing(email_id, CLASSIFICATION, "Draft")
    db.mark_sent(email_id)
    assert db.get_case(email_id)["sent_at"] is not None

    db.save_processing(email_id, CLASSIFICATION, "Draft regenerated")
    case = db.get_case(email_id)
    assert case is not None
    assert case["sent_at"] is None
    assert case["draft"] == "Draft regenerated"


def test_save_draft_unknown_returns_none(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    db.upsert_email(EMAIL)
    assert db.save_draft("nope", "Draft") is None
    assert db.mark_sent("nope") is None
    assert db.get_case("nope") is None


def test_processing_status_lifecycle(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    email_id = make_email_id(
        EMAIL["sender"], EMAIL["subject"], EMAIL["timestamp"]
    )
    db.upsert_email(EMAIL)
    assert db.list_emails()[0]["status"] == "new"
    assert db.list_pending_ids() == [email_id]

    assert db.mark_processing(email_id) is True
    assert db.list_emails()[0]["status"] == "processing"
    assert db.list_pending_ids() == [email_id]

    db.save_processing(email_id, CLASSIFICATION, "Draft")
    assert db.list_emails()[0]["status"] == "processed"
    assert db.list_pending_ids() == []

    db.mark_failed(email_id)
    assert db.list_emails()[0]["status"] == "processed"


def test_mark_failed_persists_failed_status(tmp_path) -> None:
    db = Database(str(tmp_path / "emails.db"))
    email_id = make_email_id(
        EMAIL["sender"], EMAIL["subject"], EMAIL["timestamp"]
    )
    db.upsert_email(EMAIL)
    db.mark_processing(email_id)
    assert db.mark_failed(email_id) is True
    assert db.list_emails()[0]["status"] == "failed"
    # Failed emails are not auto-retried by the pending queue.
    assert db.list_pending_ids() == []
    # Marking failed on a non-processing email is a no-op.
    assert db.mark_failed(email_id) is False
    assert db.mark_processing("nope") is False
