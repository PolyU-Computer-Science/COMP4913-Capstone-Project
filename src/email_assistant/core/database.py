"""SQLite persistence layer for emails, classifications, and drafts.

Emails are stored as tickets with standard fields (status, priority, category,
topic) plus the AI classification result and the generated draft reply. The
database path is resolved from the ``SQLITE_EMAIL_DB`` environment variable
(default ``data/emails.db``) and can be overridden per instance for testing.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=False)


def _db_path() -> str:
    return os.environ.get("SQLITE_EMAIL_DB", "data/emails.db")


def make_email_id(
    sender: str, subject: str, timestamp: str, mailbox_id: int | None = None
) -> str:
    """Derive a stable id for an email from its identifying fields.

    ``mailbox_id`` is included so the same message received by two different
    mailboxes is not collapsed into a single ticket.
    """
    raw = f"{mailbox_id}\x00{sender}\x00{subject}\x00{timestamp}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    sender TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    timestamp TEXT,
    html TEXT,
    status TEXT DEFAULT 'new',
    category TEXT,
    topic TEXT,
    priority TEXT,
    urgency_score INTEGER,
    summary TEXT,
    custom TEXT,
    draft TEXT,
    created_at TEXT,
    sent_at TEXT,
    mailbox_id INTEGER,
    topic_id INTEGER,
    topic_raw TEXT
)
"""

_ATTACHMENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY,
    email_id TEXT NOT NULL,
    cid TEXT,
    content_type TEXT,
    filename TEXT,
    data BLOB,
    UNIQUE(email_id, cid)
)
"""

_CASE_FIELD_VALUES_SCHEMA = """
CREATE TABLE IF NOT EXISTS case_field_values (
    id INTEGER PRIMARY KEY,
    case_id TEXT NOT NULL,
    field_id INTEGER NOT NULL,
    value_json TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    updated_at TEXT,
    UNIQUE(case_id, field_id)
)
"""

_DRAFT_KNOWLEDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS draft_knowledge_refs (
    id INTEGER PRIMARY KEY,
    case_id TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    chunk_id INTEGER NOT NULL,
    score REAL,
    UNIQUE(case_id, chunk_id)
)
"""

_EMAIL_COLUMNS = "id, sender, subject, body, timestamp, html, mailbox_id"

_CASE_COLUMNS = (
    f"{_EMAIL_COLUMNS}, status, category, topic, priority, "
    "summary, custom, draft, created_at, sent_at, topic_id, topic_raw"
)


def _row_to_email(row: sqlite3.Row) -> dict[str, str | int | None]:
    return {
        "id": row["id"],
        "sender": row["sender"],
        "subject": row["subject"] or "",
        "body": row["body"] or "",
        "timestamp": row["timestamp"] or "",
        "html": row["html"] or "",
        "status": row["status"] or "new",
        "mailbox_id": row["mailbox_id"] if row["mailbox_id"] is not None else None,
    }


def _row_to_case(row: sqlite3.Row) -> dict[str, Any]:
    custom_raw = row["custom"] or ""
    try:
        custom = json.loads(custom_raw) if custom_raw else {}
    except json.JSONDecodeError:
        custom = {}

    return {
        "id": row["id"],
        "email": _row_to_email(row),
        "classification": {
            "category": row["category"] or "unknown",
            "topic": row["topic"] or "",
            "priority": row["priority"] or "normal",
            "summary": row["summary"] or "",
            "custom": custom,
        },
        "draft": row["draft"] or "",
        "created_at": row["created_at"] or "",
        "sent_at": row["sent_at"] if row["sent_at"] is not None else None,
        "mailbox_id": row["mailbox_id"] if row["mailbox_id"] is not None else None,
        "topic_id": row["topic_id"] if row["topic_id"] is not None else None,
        "topic_raw": row["topic_raw"] or "",
    }


class Database:
    """Handles all database operations for the email assistant."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        path = self._db_path or _db_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute(_SCHEMA)
        conn.execute(_ATTACHMENTS_SCHEMA)
        conn.execute(_CASE_FIELD_VALUES_SCHEMA)
        conn.execute(_DRAFT_KNOWLEDGE_SCHEMA)
        try:
            conn.execute(
                "ALTER TABLE case_field_values ADD COLUMN source TEXT DEFAULT 'manual'"
            )
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE case_field_values ADD COLUMN updated_at TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE emails ADD COLUMN html TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE emails ADD COLUMN sent_at TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE emails ADD COLUMN mailbox_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE emails ADD COLUMN topic_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE emails ADD COLUMN topic_raw TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        return conn

    def upsert_email(self, email: dict) -> bool:
        """Insert an email if not already present. Returns True if newly added."""
        mailbox_id = email.get("mailbox_id")
        email_id = make_email_id(
            str(email.get("sender", "Unknown")),
            str(email.get("subject", "(no subject)")),
            str(email.get("timestamp", "")),
            mailbox_id,
        )
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO emails
                        (id, sender, subject, body, timestamp, html, mailbox_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        email_id,
                        email.get("sender", "Unknown"),
                        email.get("subject", "(no subject)"),
                        email.get("body", ""),
                        email.get("timestamp", ""),
                        email.get("html", ""),
                        mailbox_id,
                    ),
                )
                added = cur.rowcount > 0
                if added:
                    for att in email.get("attachments") or []:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO attachments
                                (email_id, cid, content_type, filename, data)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                email_id,
                                str(att.get("cid", "")),
                                str(att.get("content_type", "")),
                                str(att.get("filename", "")),
                                att.get("data") or b"",
                            ),
                        )
                conn.commit()
                return added
            finally:
                conn.close()

    def get_attachment(
        self, email_id: str, cid: str
    ) -> tuple[str, bytes] | None:
        """Return (content_type, data) for an inline attachment, or None."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT content_type, data FROM attachments "
                    "WHERE email_id = ? AND cid = ?",
                    (email_id, cid),
                ).fetchone()
            finally:
                conn.close()

        if row is None:
            return None
        return row["content_type"] or "application/octet-stream", row["data"]

    def list_emails(self, mailbox_id: int | None = None) -> list[dict]:
        """Return stored emails, newest first, optionally scoped to a mailbox."""
        with self._lock:
            conn = self._connect()
            try:
                if mailbox_id is None:
                    rows = conn.execute(
                        f"SELECT {_EMAIL_COLUMNS}, status FROM emails "
                        "ORDER BY timestamp DESC, rowid DESC"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"SELECT {_EMAIL_COLUMNS}, status FROM emails "
                        "WHERE mailbox_id = ? "
                        "ORDER BY timestamp DESC, rowid DESC",
                        (mailbox_id,),
                    ).fetchall()
            finally:
                conn.close()
        return [_row_to_email(row) for row in rows]

    def get_email(self, email_id: str) -> dict[str, str] | None:
        """Return a single email by id, or None."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    f"SELECT {_EMAIL_COLUMNS}, status FROM emails WHERE id = ?",
                    (email_id,),
                ).fetchone()
            finally:
                conn.close()
        return _row_to_email(row) if row is not None else None

    def mark_processing(self, email_id: str) -> bool:
        """Mark an email as being processed. Returns True if the email exists."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE emails SET status = 'processing' WHERE id = ?",
                    (email_id,),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def mark_failed(self, email_id: str) -> bool:
        """Mark a processing email as failed (visible in the Failed tab)."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE emails SET status = 'failed' "
                    "WHERE id = ? AND status = 'processing'",
                    (email_id,),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def list_pending_ids(self, mailbox_id: int | None = None) -> list[str]:
        """Return ids of all emails that have not been processed yet."""
        with self._lock:
            conn = self._connect()
            try:
                if mailbox_id is None:
                    rows = conn.execute(
                        "SELECT id FROM emails "
                        "WHERE status IN ('new', 'processing') "
                        "ORDER BY timestamp ASC, rowid ASC"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id FROM emails "
                        "WHERE status IN ('new', 'processing') AND mailbox_id = ? "
                        "ORDER BY timestamp ASC, rowid ASC",
                        (mailbox_id,),
                    ).fetchall()
            finally:
                conn.close()
        return [row["id"] for row in rows]

    def save_processing(
        self,
        email_id: str,
        classification: dict[str, Any],
        draft: str,
    ) -> dict[str, Any] | None:
        """Persist the classification and draft for an email. Returns the case."""
        created_at = datetime.now(timezone.utc).isoformat()
        custom_json = json.dumps(classification.get("custom") or {})

        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    UPDATE emails
                    SET status = 'processed',
                        category = ?,
                        topic = ?,
                        priority = ?,
                        summary = ?,
                        custom = ?,
                        draft = ?,
                        created_at = ?,
                        sent_at = NULL,
                        topic_id = ?,
                        topic_raw = ?
                    WHERE id = ?
                    """,
                    (
                        classification.get("category", "unknown"),
                        classification.get("topic", ""),
                        classification.get("priority", "normal"),
                        classification.get("summary", ""),
                        custom_json,
                        draft,
                        created_at,
                        classification.get("topic_id"),
                        classification.get("topic_raw", ""),
                        email_id,
                    ),
                )
                conn.commit()
                if cur.rowcount == 0:
                    return None

                row = conn.execute(
                    f"SELECT {_CASE_COLUMNS} FROM emails WHERE id = ?",
                    (email_id,),
                ).fetchone()
            finally:
                conn.close()

        return _row_to_case(row) if row is not None else None

    def get_case(self, email_id: str) -> dict[str, Any] | None:
        """Return a single processed case by email id, or None."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    f"SELECT {_CASE_COLUMNS} FROM emails "
                    "WHERE id = ? AND draft IS NOT NULL",
                    (email_id,),
                ).fetchone()
            finally:
                conn.close()
        return _row_to_case(row) if row is not None else None

    def save_draft(self, email_id: str, draft: str) -> dict[str, Any] | None:
        """Update only the draft text for a processed email."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE emails SET draft = ? WHERE id = ? AND draft IS NOT NULL",
                    (draft, email_id),
                )
                conn.commit()
                if cur.rowcount == 0:
                    return None
                row = conn.execute(
                    f"SELECT {_CASE_COLUMNS} FROM emails WHERE id = ?",
                    (email_id,),
                ).fetchone()
            finally:
                conn.close()
        return _row_to_case(row) if row is not None else None

    def mark_sent(self, email_id: str) -> dict[str, Any] | None:
        """Mark a processed case as sent. Returns the updated case."""
        sent_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE emails SET status = 'sent', sent_at = ? "
                    "WHERE id = ? AND draft IS NOT NULL",
                    (sent_at, email_id),
                )
                conn.commit()
                if cur.rowcount == 0:
                    return None
                row = conn.execute(
                    f"SELECT {_CASE_COLUMNS} FROM emails WHERE id = ?",
                    (email_id,),
                ).fetchone()
            finally:
                conn.close()
        return _row_to_case(row) if row is not None else None

    def list_cases(self, mailbox_id: int | None = None) -> list[dict[str, Any]]:
        """Return processed cases (emails with a draft), newest first."""
        with self._lock:
            conn = self._connect()
            try:
                if mailbox_id is None:
                    rows = conn.execute(
                        f"SELECT {_CASE_COLUMNS} "
                        "FROM emails WHERE draft IS NOT NULL "
                        "ORDER BY created_at DESC, rowid DESC"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"SELECT {_CASE_COLUMNS} "
                        "FROM emails WHERE draft IS NOT NULL AND mailbox_id = ? "
                        "ORDER BY created_at DESC, rowid DESC",
                        (mailbox_id,),
                    ).fetchall()
            finally:
                conn.close()
        return [_row_to_case(row) for row in rows]

    def clear(self) -> None:
        """Delete all rows (used by tests)."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM emails")
                conn.execute("DELETE FROM attachments")
                conn.execute("DELETE FROM case_field_values")
                conn.execute("DELETE FROM draft_knowledge_refs")
                conn.commit()
            finally:
                conn.close()

    def set_draft_knowledge_refs(
        self, case_id: str, refs: list[dict[str, Any]]
    ) -> None:
        """Replace the knowledge provenance for a draft."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM draft_knowledge_refs WHERE case_id = ?", (case_id,)
                )
                for ref in refs:
                    conn.execute(
                        """
                        INSERT INTO draft_knowledge_refs
                            (case_id, source_id, chunk_id, score)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            case_id,
                            int(ref["source_id"]),
                            int(ref["chunk_id"]),
                            float(ref.get("score", 0.0)),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    def get_draft_knowledge_refs(self, case_id: str) -> list[dict[str, Any]]:
        """Return knowledge provenance for a draft."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT source_id, chunk_id, score FROM draft_knowledge_refs "
                    "WHERE case_id = ? ORDER BY score DESC",
                    (case_id,),
                ).fetchall()
            finally:
                conn.close()
        return [
            {
                "source_id": row["source_id"],
                "chunk_id": row["chunk_id"],
                "score": row["score"],
            }
            for row in rows
        ]

    def backfill_missing_mailbox_ids(self, mailbox_id: int) -> int:
        """Assign all emails with NULL mailbox_id to the given mailbox.

        Used to migrate legacy emails that predate mailbox scoping. Returns
        the number of rows updated.
        """
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE emails SET mailbox_id = ? WHERE mailbox_id IS NULL",
                    (mailbox_id,),
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def count_missing_mailbox_ids(self) -> int:
        """Return the number of emails that still have NULL mailbox_id."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE mailbox_id IS NULL"
                ).fetchone()
            finally:
                conn.close()
        return int(row[0])

    # ---- case field values ----

    def get_case_field_values(self, case_id: str) -> dict[int, str]:
        """Return {field_id: value_json} for a case."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT field_id, value_json FROM case_field_values "
                    "WHERE case_id = ?",
                    (case_id,),
                ).fetchall()
            finally:
                conn.close()
        return {row["field_id"]: row["value_json"] for row in rows}

    def get_case_field_value_sources(self, case_id: str) -> dict[int, str]:
        """Return {field_id: source} for a case (``ai`` or ``manual``)."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT field_id, source FROM case_field_values "
                    "WHERE case_id = ?",
                    (case_id,),
                ).fetchall()
            finally:
                conn.close()
        return {row["field_id"]: row["source"] or "manual" for row in rows}

    def set_case_field_values(
        self, case_id: str, values: dict[int, str], source: str = "manual"
    ) -> None:
        """Upsert case field values keyed by field_id (JSON-encoded values)."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                for field_id, value_json in values.items():
                    conn.execute(
                        """
                        INSERT INTO case_field_values
                            (case_id, field_id, value_json, source, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(case_id, field_id) DO UPDATE SET
                            value_json = excluded.value_json,
                            source = excluded.source,
                            updated_at = excluded.updated_at
                        """,
                        (case_id, int(field_id), value_json, source, now),
                    )
                conn.commit()
            finally:
                conn.close()

    def set_ai_case_field_values(
        self, case_id: str, values: dict[int, str]
    ) -> None:
        """Fill AI-extracted values only for fields that are still empty.

        Existing values (especially manual ones) are never overwritten.
        """
        existing = self.get_case_field_value_sources(case_id)
        to_write = {
            field_id: value_json
            for field_id, value_json in values.items()
            if int(field_id) not in existing
        }
        if to_write:
            self.set_case_field_values(case_id, to_write, source="ai")

    def delete_case_field_value(self, case_id: str, field_id: int) -> bool:
        """Delete a single case field value. Returns True if a row was removed."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM case_field_values "
                    "WHERE case_id = ? AND field_id = ?",
                    (case_id, int(field_id)),
                )
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]
