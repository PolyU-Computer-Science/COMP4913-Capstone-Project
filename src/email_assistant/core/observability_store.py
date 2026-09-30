"""Observability store: processing runs and tool audit logs.

Both are mailbox-scoped and best-effort — writing failures must never break the
processing pipeline.
"""

from __future__ import annotations

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
    return os.environ.get("OBSERVABILITY_DB", "data/observability.db")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS processing_runs (
    id INTEGER PRIMARY KEY,
    trace_id TEXT,
    parent_run_id INTEGER,
    mailbox_id INTEGER,
    email_id TEXT,
    case_id TEXT,
    stage TEXT,
    status TEXT DEFAULT 'running',
    provider TEXT,
    model TEXT,
    started_at TEXT,
    completed_at TEXT,
    latency_ms REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    metadata_json TEXT DEFAULT '{}',
    error_type TEXT,
    error_message TEXT,
    created_at TEXT
)
"""

_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_audit_logs (
    id INTEGER PRIMARY KEY,
    mailbox_id INTEGER,
    email_id TEXT,
    case_id TEXT,
    connector_id INTEGER,
    tool_name TEXT,
    arguments_json_redacted TEXT DEFAULT '{}',
    status TEXT,
    started_at TEXT,
    completed_at TEXT,
    latency_ms REAL,
    result_summary TEXT,
    error_type TEXT,
    error_message TEXT,
    created_at TEXT
)
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ObservabilityStore:
    """Persistent store for processing runs and tool audit logs."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _db_path()
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(_SCHEMA)
        conn.execute(_AUDIT_SCHEMA)
        conn.commit()
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        conn.close()

    # ---- processing runs ----

    def start_run(self, data: dict[str, Any]) -> int:
        now = _now()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO processing_runs
                        (trace_id, parent_run_id, mailbox_id, email_id, case_id,
                         stage, status, provider, model, started_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data.get("trace_id"),
                        data.get("parent_run_id"),
                        data.get("mailbox_id"),
                        data.get("email_id"),
                        data.get("case_id"),
                        data.get("stage", "email_processing"),
                        "running",
                        data.get("provider"),
                        data.get("model"),
                        now,
                        now,
                    ),
                )
                conn.commit()
                run_id = cur.lastrowid
            finally:
                conn.close()
        return int(run_id)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str = "success",
        latency_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = _now()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE processing_runs
                    SET status = ?, completed_at = ?, latency_ms = ?,
                        input_tokens = ?, output_tokens = ?, total_tokens = ?,
                        metadata_json = ?, error_type = ?, error_message = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        now,
                        latency_ms,
                        input_tokens,
                        output_tokens,
                        total_tokens,
                        json.dumps(metadata or {}),
                        error_type,
                        error_message,
                        run_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def record_usage(
        self,
        run_id: int,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        """Update only the token columns of a finished run."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE processing_runs SET input_tokens = ?, "
                    "output_tokens = ?, total_tokens = ? WHERE id = ?",
                    (input_tokens, output_tokens, total_tokens, run_id),
                )
                conn.commit()
            finally:
                conn.close()

    def attach_metadata(self, run_id: int, metadata: dict[str, Any]) -> None:
        """Replace the metadata of a finished run (used for stage stats)."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE processing_runs SET metadata_json = ? WHERE id = ?",
                    (json.dumps(metadata or {}), run_id),
                )
                conn.commit()
            finally:
                conn.close()

    def list_runs(
        self,
        mailbox_id: int | None = None,
        email_id: str | None = None,
        stage: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM processing_runs"
        clauses: list[str] = []
        params: list[Any] = []
        if mailbox_id is not None:
            clauses.append("mailbox_id = ?")
            params.append(mailbox_id)
        if email_id is not None:
            clauses.append("email_id = ?")
            params.append(email_id)
        if stage is not None:
            clauses.append("stage = ?")
            params.append(stage)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(query, params).fetchall()
            finally:
                conn.close()
        return [dict(row) for row in rows]

    def get_email_subject(self, email_id: str) -> str | None:
        """Look up an email's subject from the email store (best effort)."""
        try:
            from email_assistant.core.database import Database

            db = Database()
            with db._lock:
                conn = db._connect()
                try:
                    row = conn.execute(
                        "SELECT subject FROM emails WHERE id = ?", (email_id,)
                    ).fetchone()
                finally:
                    conn.close()
            return str(row["subject"]) if row else None
        except Exception:  # noqa: BLE001 - subject display is best effort
            return None

    # ---- tool audit ----

    def audit_tool_call(
        self,
        mailbox_id: int | None,
        connector_id: int,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        status: str,
        result_summary: str = "",
        latency_ms: float | None = None,
        email_id: str | None = None,
        case_id: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = _now()
        # Redact: never store raw arguments verbatim (may contain secrets).
        redacted = _redact(arguments)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO tool_audit_logs
                        (mailbox_id, email_id, case_id, connector_id, tool_name,
                         arguments_json_redacted, status, started_at,
                         completed_at, latency_ms, result_summary, error_type,
                         error_message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mailbox_id,
                        email_id,
                        case_id,
                        connector_id,
                        tool_name,
                        json.dumps(redacted),
                        status,
                        now,
                        now,
                        latency_ms,
                        result_summary[:500],
                        error_type,
                        error_message,
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def list_audit_logs(
        self, mailbox_id: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM tool_audit_logs WHERE mailbox_id = ? "
                    "ORDER BY id DESC LIMIT ?",
                    (mailbox_id, limit),
                ).fetchall()
            finally:
                conn.close()
        return [dict(row) for row in rows]

    def clear(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM processing_runs")
                conn.execute("DELETE FROM tool_audit_logs")
                conn.commit()
            finally:
                conn.close()


_SECRET_KEYS = {
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "credential",
}


def _redact(arguments: dict[str, Any]) -> dict[str, Any]:
    """Shallow-redact obvious secret keys in tool arguments."""
    redacted: dict[str, Any] = {}
    for key, value in arguments.items():
        lowered = str(key).lower()
        if any(secret in lowered for secret in _SECRET_KEYS):
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted
