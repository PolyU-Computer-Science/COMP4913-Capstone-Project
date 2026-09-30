"""SQLite-backed settings store with Fernet-encrypted secrets.

Stores:
- ``ai_configs`` — multiple LLM configurations, one marked active.
- ``settings`` — global per-stage settings (system prompt, task prompt,
  generation params) for the ``classification`` and ``draft`` stages.
- ``mail_accounts`` — IMAP mail accounts.
- ``mailboxes`` — business email contexts (name, purpose, connection, AI
  behaviour, instructions) that group topics, fields, knowledge and connectors.
- ``topics`` / ``custom_fields`` — per-mailbox taxonomy and custom fields.
- ``knowledge_sources`` — global reusable knowledge resources, assigned to
  mailboxes via ``mailbox_knowledge``.
- ``connectors`` — global external tools (MCP), enabled per mailbox with
  per-tool permissions via ``mailbox_connectors``.

Environment variables remain the defaults; values saved here override them at
runtime. API keys and mail passwords are encrypted with Fernet before being
written to disk.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv(override=False)

STAGES = ("classification", "draft")
STAGE_FIELDS = ("role", "goal", "backstory", "prompt", "max_tokens", "temperature")

SECRETS_DIR_FILENAME = ".secret_key"


def _db_path() -> str:
    return os.environ.get("SQLITE_SETTINGS_DB", "data/settings.db")


def _load_encryption_key() -> bytes:
    """Return the Fernet key from env, else a persisted key file."""
    from_env = os.environ.get("SETTINGS_ENCRYPTION_KEY", "").strip()
    if from_env:
        return from_env.encode()

    data_dir = Path(_db_path()).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_file = data_dir / SECRETS_DIR_FILENAME

    if secret_file.exists():
        return secret_file.read_text().strip().encode()

    key = Fernet.generate_key().decode()
    secret_file.write_text(key)
    return key.encode()


class SettingsStore:
    """Persistent store for AI configs, stage settings, and mail accounts."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _db_path()
        self._lock = threading.Lock()
        self._fernet = Fernet(_load_encryption_key())
        self._init_db()

    # ---- infrastructure ----

    def _connect(self) -> sqlite3.Connection:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS settings "
                    "(key TEXT PRIMARY KEY, value TEXT)"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ai_configs (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        base_url TEXT,
                        api_key TEXT,
                        timeout REAL,
                        max_tokens INTEGER,
                        temperature REAL,
                        enabled INTEGER DEFAULT 0
                    )
                    """
                )
                for column, col_type in (("max_tokens", "INTEGER"), ("temperature", "REAL")):
                    try:
                        conn.execute(
                            f"ALTER TABLE ai_configs ADD COLUMN {column} {col_type}"
                        )
                    except sqlite3.OperationalError:
                        pass
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mail_accounts (
                        id INTEGER PRIMARY KEY,
                        name TEXT DEFAULT '',
                        address TEXT NOT NULL,
                        imap_host TEXT,
                        imap_port INTEGER,
                        smtp_host TEXT,
                        smtp_port INTEGER,
                        password TEXT,
                        max_emails INTEGER DEFAULT 50,
                        enabled INTEGER DEFAULT 1
                    )
                    """
                )
                for column, col_type in (
                    ("name", "TEXT DEFAULT ''"),
                    ("max_emails", "INTEGER DEFAULT 50"),
                ):
                    try:
                        conn.execute(
                            f"ALTER TABLE mail_accounts ADD COLUMN {column} {col_type}"
                        )
                    except sqlite3.OperationalError:
                        pass
                self._create_mailbox_tables(conn)
                conn.commit()
            finally:
                conn.close()

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def _decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()

    @staticmethod
    def _create_mailbox_tables(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mailboxes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                purpose TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                imap_host TEXT DEFAULT '',
                imap_port INTEGER DEFAULT 993,
                imap_security TEXT DEFAULT 'ssl',
                imap_folder TEXT DEFAULT 'INBOX',
                smtp_host TEXT DEFAULT '',
                smtp_port INTEGER DEFAULT 587,
                smtp_security TEXT DEFAULT 'starttls',
                password TEXT DEFAULT '',
                max_emails INTEGER DEFAULT 50,
                auto_process INTEGER DEFAULT 0,
                generate_drafts INTEGER DEFAULT 1,
                human_approval INTEGER DEFAULT 1,
                classifier_config_id INTEGER,
                drafter_config_id INTEGER,
                classifier_temperature REAL,
                classifier_max_tokens INTEGER,
                drafter_temperature REAL,
                drafter_max_tokens INTEGER,
                use_knowledge INTEGER DEFAULT 0,
                instructions TEXT DEFAULT '',
                is_system INTEGER DEFAULT 0
            )
            """
        )
        try:
            conn.execute(
                "ALTER TABLE mailboxes ADD COLUMN is_system INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY,
                mailbox_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'active'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_fields (
                id INTEGER PRIMARY KEY,
                mailbox_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'text',
                required INTEGER DEFAULT 0,
                options TEXT DEFAULT '',
                prompt TEXT DEFAULT '',
                status TEXT DEFAULT 'active'
            )
            """
        )
        try:
            conn.execute("ALTER TABLE custom_fields ADD COLUMN prompt TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_sources (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'document',
                status TEXT DEFAULT 'ready',
                chunks INTEGER DEFAULT 0
            )
            """
        )
        try:
            conn.execute(
                "ALTER TABLE knowledge_sources ADD COLUMN content TEXT DEFAULT ''"
            )
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mailbox_knowledge (
                mailbox_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                PRIMARY KEY (mailbox_id, source_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connectors (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'mcp',
                server TEXT DEFAULT '',
                status TEXT DEFAULT 'disconnected'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mailbox_connectors (
                mailbox_id INTEGER NOT NULL,
                connector_id INTEGER NOT NULL,
                enabled INTEGER DEFAULT 1,
                allowed_tools TEXT DEFAULT '',
                PRIMARY KEY (mailbox_id, connector_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connector_tool_permissions (
                id INTEGER PRIMARY KEY,
                mailbox_id INTEGER NOT NULL,
                connector_id INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                enabled INTEGER DEFAULT 0,
                permission_level TEXT DEFAULT 'read',
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(mailbox_id, connector_id, tool_name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS connector_tools (
                id INTEGER PRIMARY KEY,
                connector_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                input_schema_json TEXT DEFAULT '{}',
                output_schema_json TEXT DEFAULT '{}',
                annotations_json TEXT DEFAULT '{}',
                enabled INTEGER DEFAULT 0,
                risk_level TEXT DEFAULT 'read',
                discovered_at TEXT,
                updated_at TEXT,
                UNIQUE(connector_id, name)
            )
            """
        )

    # ---- AI configs ----

    def _ai_row_to_dict(
        self, row: sqlite3.Row, mask_secrets: bool
    ) -> dict[str, Any]:
        account = dict(row)
        account["enabled"] = bool(account["enabled"])
        account["max_tokens"] = int(account.get("max_tokens") or 8000)
        account["temperature"] = float(account.get("temperature") or 0.2)
        encrypted = account.get("api_key") or ""
        if mask_secrets:
            account["api_key"] = ""
            account["has_api_key"] = bool(encrypted)
        elif encrypted:
            account["api_key"] = self._decrypt(encrypted)
        return account

    def list_ai_configs(self, mask_secrets: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM ai_configs ORDER BY id"
                ).fetchall()
            finally:
                conn.close()

        return [
            self._ai_row_to_dict(row, mask_secrets) for row in rows
        ]

    def get_ai_config(
        self, config_id: int, mask_secrets: bool = True
    ) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM ai_configs WHERE id = ?", (config_id,)
                ).fetchone()
            finally:
                conn.close()

        if row is None:
            return None
        return self._ai_row_to_dict(row, mask_secrets)

    def get_active_ai_config(self) -> dict[str, Any] | None:
        """Return the active config with a decrypted api key."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM ai_configs WHERE enabled = 1 "
                    "ORDER BY id LIMIT 1"
                ).fetchone()
            finally:
                conn.close()

        if row is None:
            return None
        return self._ai_row_to_dict(row, mask_secrets=False)

    def _deactivate_all(self, conn: sqlite3.Connection) -> None:
        conn.execute("UPDATE ai_configs SET enabled = 0")

    def create_ai_config(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM ai_configs"
                ).fetchone()[0]
                enabled = 1 if (data.get("enabled") or count == 0) else 0
                if enabled:
                    self._deactivate_all(conn)

                password = str(data.get("api_key") or "")
                encrypted = self._encrypt(password) if password else ""
                cur = conn.execute(
                    """
                    INSERT INTO ai_configs
                        (name, provider, model, base_url, api_key,
                         timeout, max_tokens, temperature, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(data.get("name", "")),
                        str(data.get("provider", "")),
                        str(data.get("model", "")),
                        str(data.get("base_url", "")),
                        encrypted,
                        float(data.get("timeout", 120)),
                        int(data.get("max_tokens", 8000)),
                        float(data.get("temperature", 0.2)),
                        enabled,
                    ),
                )
                config_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()

        config = self.get_ai_config(config_id)  # type: ignore[arg-type]
        assert config is not None
        return config

    def update_ai_config(
        self, config_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        existing = self.get_ai_config(config_id, mask_secrets=False)
        if existing is None:
            return None

        merged = {**existing, **data}
        if str(data.get("api_key") or "") == "":
            merged["api_key"] = existing["api_key"]  # keep existing

        with self._lock:
            conn = self._connect()
            try:
                if merged.get("enabled"):
                    self._deactivate_all(conn)
                password = str(merged.get("api_key") or "")
                encrypted = self._encrypt(password) if password else ""
                conn.execute(
                    """
                    UPDATE ai_configs
                    SET name = ?, provider = ?, model = ?, base_url = ?,
                        api_key = ?, timeout = ?, max_tokens = ?,
                        temperature = ?, enabled = ?
                    WHERE id = ?
                    """,
                    (
                        str(merged.get("name", "")),
                        str(merged.get("provider", "")),
                        str(merged.get("model", "")),
                        str(merged.get("base_url", "")),
                        encrypted,
                        float(merged.get("timeout", 120)),
                        int(merged.get("max_tokens", 8000)),
                        float(merged.get("temperature", 0.2)),
                        1 if merged.get("enabled") else 0,
                        config_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        return self.get_ai_config(config_id)

    def delete_ai_config(self, config_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM ai_configs WHERE id = ?", (config_id,)
                )
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]

    def set_active_ai_config(self, config_id: int) -> dict[str, Any] | None:
        if self.get_ai_config(config_id) is None:
            return None

        with self._lock:
            conn = self._connect()
            try:
                self._deactivate_all(conn)
                conn.execute(
                    "UPDATE ai_configs SET enabled = 1 WHERE id = ?",
                    (config_id,),
                )
                conn.commit()
            finally:
                conn.close()

        return self.get_ai_config(config_id)

    def ensure_default_ai_config(self) -> dict[str, Any] | None:
        """Seed a default AI config from env when none exist. Returns it, or None."""
        with self._lock:
            conn = self._connect()
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM ai_configs"
                ).fetchone()[0]
            finally:
                conn.close()

        if count > 0:
            return None

        from email_assistant.service import LLMSettings

        try:
            settings = LLMSettings.from_env()
        except Exception:
            return None

        api_key = settings.api_key.get_secret_value() if settings.api_key else ""
        return self.create_ai_config(
            {
                "name": "Default",
                "provider": settings.provider.value,
                "model": settings.model,
                "base_url": settings.base_url or "",
                "api_key": api_key,
                "timeout": settings.timeout,
                "max_tokens": settings.max_tokens,
                "temperature": settings.temperature,
                "enabled": True,
            }
        )

    # ---- stage settings ----

    def ensure_default_stage_settings(self) -> bool:
        """Seed built-in stage defaults into the DB once.

        Returns True if seeding happened. Never overwrites existing
        stage settings — user edits always win.
        """
        from email_assistant.core.stage_seeds import STAGE_SEEDS

        with self._lock:
            conn = self._connect()
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM settings WHERE key LIKE 'stage.%'"
                ).fetchone()[0]
                if count > 0:
                    return False
                for stage, defaults in STAGE_SEEDS.items():
                    for field in ("role", "goal", "backstory", "prompt"):
                        value = defaults.get(field) or ""
                        if value:
                            conn.execute(
                                "INSERT OR REPLACE INTO settings (key, value) "
                                "VALUES (?, ?)",
                                (f"stage.{stage}.{field}", value),
                            )
                conn.commit()
                return True
            finally:
                conn.close()
    def get_stage_settings(self, stage: str) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT key, value FROM settings WHERE key LIKE ?",
                    (f"stage.{stage}.%",),
                ).fetchall()
            finally:
                conn.close()

        prefix = f"stage.{stage}."
        raw = {row["key"][len(prefix):]: row["value"] for row in rows}

        result: dict[str, Any] = {
            "role": "",
            "goal": "",
            "backstory": "",
            "prompt": "",
            "max_tokens": None,
            "temperature": None,
        }
        for field in ("role", "goal", "backstory", "prompt"):
            result[field] = raw.get(field, "")
        if raw.get("max_tokens", ""):
            result["max_tokens"] = int(raw["max_tokens"])
        if raw.get("temperature", ""):
            result["temperature"] = float(raw["temperature"])
        return result

    def set_stage_settings(self, stage: str, data: dict[str, Any]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                for field in STAGE_FIELDS:
                    if field not in data:
                        continue
                    value = data[field]
                    key = f"stage.{stage}.{field}"
                    if value is None or (isinstance(value, str) and not value.strip()):
                        conn.execute(
                            "DELETE FROM settings WHERE key = ?", (key,)
                        )
                        continue
                    conn.execute(
                        "INSERT INTO settings (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (key, str(value)),
                    )
                conn.commit()
            finally:
                conn.close()

    # ---- mail accounts ----

    def list_mail_accounts(self, mask_secrets: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM mail_accounts ORDER BY id"
                ).fetchall()
            finally:
                conn.close()

        accounts = []
        for row in rows:
            account = dict(row)
            account["name"] = str(account.get("name") or "")
            account["enabled"] = bool(account["enabled"])
            encrypted = account.get("password") or ""
            if mask_secrets:
                account["password"] = ""
                account["has_password"] = bool(encrypted)
            elif encrypted:
                account["password"] = self._decrypt(encrypted)
            accounts.append(account)
        return accounts

    def get_mail_account(
        self, account_id: int, mask_secrets: bool = True
    ) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM mail_accounts WHERE id = ?", (account_id,)
                ).fetchone()
            finally:
                conn.close()

        if row is None:
            return None

        account = dict(row)
        account["name"] = str(account.get("name") or "")
        account["enabled"] = bool(account["enabled"])
        encrypted = account.get("password") or ""
        if mask_secrets:
            account["password"] = ""
            account["has_password"] = bool(encrypted)
        elif encrypted:
            account["password"] = self._decrypt(encrypted)
        return account

    def get_enabled_mail_account(self) -> dict[str, Any] | None:
        """Return the first enabled mail account with a decrypted password."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM mail_accounts WHERE enabled = 1 ORDER BY id LIMIT 1"
                ).fetchone()
            finally:
                conn.close()

        if row is None:
            return None

        account = dict(row)
        account["name"] = str(account.get("name") or "")
        account["enabled"] = bool(account["enabled"])
        encrypted = account.get("password") or ""
        account["password"] = self._decrypt(encrypted) if encrypted else ""
        return account

    def create_mail_account(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                password = str(data.get("password") or "")
                encrypted = self._encrypt(password) if password else ""
                cur = conn.execute(
                    """
                    INSERT INTO mail_accounts
                        (name, address, imap_host, imap_port, smtp_host, smtp_port,
                         password, max_emails, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(data.get("name", "") or ""),
                        str(data.get("address", "")),
                        str(data.get("imap_host", "")),
                        int(data.get("imap_port", 993)),
                        str(data.get("smtp_host", "")),
                        int(data.get("smtp_port", 587)),
                        encrypted,
                        int(data.get("max_emails", 50)),
                        1 if data.get("enabled", True) else 0,
                    ),
                )
                account_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()

        account = self.get_mail_account(account_id)  # type: ignore[arg-type]
        assert account is not None
        return account

    def update_mail_account(
        self, account_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        existing = self.get_mail_account(account_id, mask_secrets=False)
        if existing is None:
            return None

        merged = {**existing, **data}
        if str(data.get("password") or "") == "":
            merged["password"] = existing["password"]  # keep existing

        with self._lock:
            conn = self._connect()
            try:
                password = str(merged.get("password") or "")
                encrypted = self._encrypt(password) if password else ""
                conn.execute(
                    """
                    UPDATE mail_accounts
                    SET name = ?, address = ?, imap_host = ?, imap_port = ?,
                        smtp_host = ?, smtp_port = ?, password = ?,
                        max_emails = ?, enabled = ?
                    WHERE id = ?
                    """,
                    (
                        str(merged.get("name", "") or ""),
                        str(merged.get("address", "")),
                        str(merged.get("imap_host", "")),
                        int(merged.get("imap_port", 993)),
                        str(merged.get("smtp_host", "")),
                        int(merged.get("smtp_port", 587)),
                        encrypted,
                        int(merged.get("max_emails", 50)),
                        1 if merged.get("enabled", True) else 0,
                        account_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        return self.get_mail_account(account_id)

    def delete_mail_account(self, account_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM mail_accounts WHERE id = ?", (account_id,)
                )
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]

    # ---- mailboxes ----

    def _mailbox_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        mailbox = dict(row)
        for field in (
            "imap_port",
            "smtp_port",
            "max_emails",
            "classifier_config_id",
            "drafter_config_id",
            "classifier_max_tokens",
            "drafter_max_tokens",
        ):
            value = mailbox.get(field)
            mailbox[field] = int(value) if value is not None else None
        for field in (
            "classifier_temperature",
            "drafter_temperature",
        ):
            value = mailbox.get(field)
            mailbox[field] = float(value) if value is not None else None
        for field in ("auto_process", "generate_drafts", "human_approval", "use_knowledge"):
            mailbox[field] = bool(mailbox.get(field))
        mailbox["is_system"] = bool(mailbox.get("is_system"))
        return mailbox

    def list_mailboxes(self, include_system: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                if include_system:
                    rows = conn.execute(
                        "SELECT * FROM mailboxes ORDER BY id"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM mailboxes WHERE is_system = 0 ORDER BY id"
                    ).fetchall()
            finally:
                conn.close()
        return [self._mailbox_row_to_dict(row) for row in rows]

    def get_mailbox_by_name(self, name: str) -> dict[str, Any] | None:
        """Return a mailbox by exact name, or None."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM mailboxes WHERE name = ?", (name,)
                ).fetchone()
            finally:
                conn.close()
        return self._mailbox_row_to_dict(row) if row is not None else None

    def get_mailbox(self, mailbox_id: int) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM mailboxes WHERE id = ?", (mailbox_id,)
                ).fetchone()
            finally:
                conn.close()
        return self._mailbox_row_to_dict(row) if row is not None else None

    def ensure_default_mailbox(self) -> bool:
        """Seed the built-in default mailbox (topics + fields) once.

        Runs only when the mailboxes table is empty — never overwrites
        existing mailboxes. The password is NOT seeded; it must be set
        via the UI. Returns True if seeding happened.
        """
        from email_assistant.core.mailbox_seeds import (
            FIELD_SEEDS,
            MAILBOX_SEED,
            TOPIC_SEEDS,
            _env_password,
        )

        with self._lock:
            conn = self._connect()
            try:
                count = conn.execute("SELECT COUNT(*) FROM mailboxes").fetchone()[0]
            finally:
                conn.close()
        if count > 0:
            return False

        mailbox = self.create_mailbox(MAILBOX_SEED)
        mailbox_id = int(mailbox["id"])
        password = _env_password()
        if password:
            self.set_mailbox_password(mailbox_id, password)
        for topic in TOPIC_SEEDS:
            self.create_topic(mailbox_id, {**topic, "status": "active"})
        for field in FIELD_SEEDS:
            self.create_custom_field(mailbox_id, {**field, "required": False, "status": "active"})
        return True

    def create_mailbox(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO mailboxes (
                        name, address, purpose, status, imap_host, imap_port,
                        imap_security, imap_folder, smtp_host, smtp_port,
                        smtp_security, password, max_emails, auto_process,
                        generate_drafts, human_approval, classifier_config_id,
                        drafter_config_id, classifier_temperature,
                        classifier_max_tokens, drafter_temperature,
                        drafter_max_tokens, use_knowledge, instructions,
                        is_system
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(data.get("name", "")),
                        str(data.get("address", "")),
                        str(data.get("purpose", "")),
                        str(data.get("status", "active")),
                        str(data.get("imap_host", "")),
                        int(data.get("imap_port", 993)),
                        str(data.get("imap_security", "ssl")),
                        str(data.get("imap_folder", "INBOX")),
                        str(data.get("smtp_host", "")),
                        int(data.get("smtp_port", 587)),
                        str(data.get("smtp_security", "starttls")),
                        "",
                        int(data.get("max_emails", 50)),
                        1 if data.get("auto_process") else 0,
                        1 if data.get("generate_drafts", True) else 0,
                        1 if data.get("human_approval", True) else 0,
                        data.get("classifier_config_id"),
                        data.get("drafter_config_id"),
                        data.get("classifier_temperature"),
                        data.get("classifier_max_tokens"),
                        data.get("drafter_temperature"),
                        data.get("drafter_max_tokens"),
                        1 if data.get("use_knowledge") else 0,
                        str(data.get("instructions", "")),
                        1 if data.get("is_system") else 0,
                    ),
                )
                mailbox_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()

        mailbox = self.get_mailbox(mailbox_id)  # type: ignore[arg-type]
        assert mailbox is not None
        return mailbox

    def update_mailbox(
        self, mailbox_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        existing = self.get_mailbox(mailbox_id)
        if existing is None:
            return None
        merged = {**existing, **data}

        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE mailboxes
                    SET name = ?, address = ?, purpose = ?, status = ?,
                        imap_host = ?, imap_port = ?, imap_security = ?,
                        imap_folder = ?, smtp_host = ?, smtp_port = ?,
                        smtp_security = ?, max_emails = ?, auto_process = ?,
                        generate_drafts = ?, human_approval = ?,
                        classifier_config_id = ?, drafter_config_id = ?,
                        classifier_temperature = ?, classifier_max_tokens = ?,
                        drafter_temperature = ?, drafter_max_tokens = ?,
                        use_knowledge = ?, instructions = ?
                    WHERE id = ?
                    """,
                    (
                        str(merged.get("name", "")),
                        str(merged.get("address", "")),
                        str(merged.get("purpose", "")),
                        str(merged.get("status", "active")),
                        str(merged.get("imap_host", "")),
                        int(merged.get("imap_port", 993)),
                        str(merged.get("imap_security", "ssl")),
                        str(merged.get("imap_folder", "INBOX")),
                        str(merged.get("smtp_host", "")),
                        int(merged.get("smtp_port", 587)),
                        str(merged.get("smtp_security", "starttls")),
                        int(merged.get("max_emails", 50)),
                        1 if merged.get("auto_process") else 0,
                        1 if merged.get("generate_drafts", True) else 0,
                        1 if merged.get("human_approval", True) else 0,
                        merged.get("classifier_config_id"),
                        merged.get("drafter_config_id"),
                        merged.get("classifier_temperature"),
                        merged.get("classifier_max_tokens"),
                        merged.get("drafter_temperature"),
                        merged.get("drafter_max_tokens"),
                        1 if merged.get("use_knowledge") else 0,
                        str(merged.get("instructions", "")),
                        mailbox_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        return self.get_mailbox(mailbox_id)

    def set_mailbox_password(self, mailbox_id: int, password: str) -> bool:
        """Store an encrypted IMAP/SMTP password for a mailbox."""
        if self.get_mailbox(mailbox_id) is None:
            return False
        encrypted = self._encrypt(password) if password else ""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE mailboxes SET password = ? WHERE id = ?",
                    (encrypted, mailbox_id),
                )
                conn.commit()
            finally:
                conn.close()
        return True

    def get_mailbox_password(self, mailbox_id: int) -> str | None:
        """Return the decrypted mailbox password, or None."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT password FROM mailboxes WHERE id = ?", (mailbox_id,)
                ).fetchone()
            finally:
                conn.close()
        if row is None or not row["password"]:
            return None
        return self._decrypt(row["password"])

    def delete_mailbox(self, mailbox_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM mailboxes WHERE id = ?", (mailbox_id,)
                )
                conn.execute(
                    "DELETE FROM mailbox_knowledge WHERE mailbox_id = ?",
                    (mailbox_id,),
                )
                conn.execute(
                    "DELETE FROM mailbox_connectors WHERE mailbox_id = ?",
                    (mailbox_id,),
                )
                conn.execute(
                    "DELETE FROM topics WHERE mailbox_id = ?", (mailbox_id,)
                )
                conn.execute(
                    "DELETE FROM custom_fields WHERE mailbox_id = ?", (mailbox_id,)
                )
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]

    # ---- topics ----

    def list_topics(self, mailbox_id: int) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM topics WHERE mailbox_id = ? ORDER BY id",
                    (mailbox_id,),
                ).fetchall()
            finally:
                conn.close()
        topics = []
        for row in rows:
            topic = dict(row)
            topic["status"] = topic.get("status") or "active"
            topics.append(topic)
        return topics

    def create_topic(self, mailbox_id: int, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO topics (mailbox_id, name, description, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        mailbox_id,
                        str(data.get("name", "")),
                        str(data.get("description", "")),
                        str(data.get("status", "active")),
                    ),
                )
                topic_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()
        return self.get_topic(topic_id)  # type: ignore[arg-type]

    def get_topic(self, topic_id: int) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM topics WHERE id = ?", (topic_id,)
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        topic = dict(row)
        topic["status"] = topic.get("status") or "active"
        return topic

    def update_topic(self, topic_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get_topic(topic_id)
        if existing is None:
            return None
        merged = {**existing, **data}
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE topics SET name = ?, description = ?, status = ?
                    WHERE id = ?
                    """,
                    (
                        str(merged.get("name", "")),
                        str(merged.get("description", "")),
                        str(merged.get("status", "active")),
                        topic_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_topic(topic_id)

    def delete_topic(self, topic_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]

    # ---- custom fields ----

    def list_custom_fields(self, mailbox_id: int) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM custom_fields WHERE mailbox_id = ? ORDER BY id",
                    (mailbox_id,),
                ).fetchall()
            finally:
                conn.close()
        fields = []
        for row in rows:
            field = dict(row)
            field["type"] = field.get("type") or "text"
            field["required"] = bool(field.get("required"))
            field["status"] = field.get("status") or "active"
            field["options"] = field.get("options") or ""
            field["prompt"] = field.get("prompt") or ""
            fields.append(field)
        return fields

    def create_custom_field(
        self, mailbox_id: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO custom_fields
                        (mailbox_id, name, type, required, options, prompt, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mailbox_id,
                        str(data.get("name", "")),
                        str(data.get("type", "text")),
                        1 if data.get("required") else 0,
                        str(data.get("options", "")),
                        str(data.get("prompt", "")),
                        str(data.get("status", "active")),
                    ),
                )
                field_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()
        return self.get_custom_field(field_id)  # type: ignore[arg-type]

    def get_custom_field(self, field_id: int) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM custom_fields WHERE id = ?", (field_id,)
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        field = dict(row)
        field["type"] = field.get("type") or "text"
        field["required"] = bool(field.get("required"))
        field["status"] = field.get("status") or "active"
        field["options"] = field.get("options") or ""
        field["prompt"] = field.get("prompt") or ""
        return field

    def update_custom_field(
        self, field_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        existing = self.get_custom_field(field_id)
        if existing is None:
            return None
        merged = {**existing, **data}
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE custom_fields SET name = ?, type = ?, required = ?,
                        options = ?, prompt = ?, status = ?
                    WHERE id = ?
                    """,
                    (
                        str(merged.get("name", "")),
                        str(merged.get("type", "text")),
                        1 if merged.get("required") else 0,
                        str(merged.get("options", "")),
                        str(merged.get("prompt", "")),
                        str(merged.get("status", "active")),
                        field_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_custom_field(field_id)

    def delete_custom_field(self, field_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM custom_fields WHERE id = ?", (field_id,)
                )
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]

    # ---- knowledge sources ----

    def list_knowledge_sources(self) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM knowledge_sources ORDER BY id"
                ).fetchall()
            finally:
                conn.close()
        sources = []
        for row in rows:
            source = dict(row)
            source["type"] = source.get("type") or "document"
            source["status"] = source.get("status") or "ready"
            source["chunks"] = int(source.get("chunks") or 0)
            sources.append(source)
        return sources

    def get_knowledge_source(self, source_id: int) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM knowledge_sources WHERE id = ?", (source_id,)
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        source = dict(row)
        source["type"] = source.get("type") or "document"
        source["status"] = source.get("status") or "ready"
        source["chunks"] = int(source.get("chunks") or 0)
        return source

    def create_knowledge_source(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO knowledge_sources (name, type, status, chunks, content)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(data.get("name", "")),
                        str(data.get("type", "document")),
                        str(data.get("status", "ready")),
                        int(data.get("chunks", 0)),
                        str(data.get("content", "")),
                    ),
                )
                source_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()
        return self.get_knowledge_source(source_id)  # type: ignore[arg-type]

    def update_knowledge_source(
        self, source_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        existing = self.get_knowledge_source(source_id)
        if existing is None:
            return None
        merged = {**existing, **data}
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE knowledge_sources SET name = ?, type = ?, status = ?,
                        chunks = ?, content = ?
                    WHERE id = ?
                    """,
                    (
                        str(merged.get("name", "")),
                        str(merged.get("type", "document")),
                        str(merged.get("status", "ready")),
                        int(merged.get("chunks", 0)),
                        str(merged.get("content", "")),
                        source_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_knowledge_source(source_id)

    def delete_knowledge_source(self, source_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM knowledge_sources WHERE id = ?", (source_id,)
                )
                conn.execute(
                    "DELETE FROM mailbox_knowledge WHERE source_id = ?", (source_id,)
                )
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]

    def list_mailbox_knowledge(self, mailbox_id: int) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT ks.* FROM knowledge_sources ks
                    JOIN mailbox_knowledge mk ON mk.source_id = ks.id
                    WHERE mk.mailbox_id = ?
                    ORDER BY ks.id
                    """,
                    (mailbox_id,),
                ).fetchall()
            finally:
                conn.close()
        sources = []
        for row in rows:
            source = dict(row)
            source["type"] = source.get("type") or "document"
            source["status"] = source.get("status") or "ready"
            source["chunks"] = int(source.get("chunks") or 0)
            sources.append(source)
        return sources

    def assign_knowledge(self, mailbox_id: int, source_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO mailbox_knowledge (mailbox_id, source_id) "
                    "VALUES (?, ?)",
                    (mailbox_id, source_id),
                )
                conn.commit()
            finally:
                conn.close()
        return True

    def unassign_knowledge(self, mailbox_id: int, source_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM mailbox_knowledge WHERE mailbox_id = ? AND source_id = ?",
                    (mailbox_id, source_id),
                )
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]

    # ---- connectors ----

    def list_connectors(self) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT * FROM connectors ORDER BY id").fetchall()
            finally:
                conn.close()
        connectors = []
        for row in rows:
            connector = dict(row)
            connector["type"] = connector.get("type") or "mcp"
            connector["status"] = connector.get("status") or "disconnected"
            connectors.append(connector)
        return connectors

    def get_connector(self, connector_id: int) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM connectors WHERE id = ?", (connector_id,)
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        connector = dict(row)
        connector["type"] = connector.get("type") or "mcp"
        connector["status"] = connector.get("status") or "disconnected"
        return connector

    def create_connector(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO connectors (name, type, server, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(data.get("name", "")),
                        str(data.get("type", "mcp")),
                        str(data.get("server", "")),
                        str(data.get("status", "disconnected")),
                    ),
                )
                connector_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()
        return self.get_connector(connector_id)  # type: ignore[arg-type]

    def update_connector(
        self, connector_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        existing = self.get_connector(connector_id)
        if existing is None:
            return None
        merged = {**existing, **data}
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE connectors SET name = ?, type = ?, server = ?, status = ?
                    WHERE id = ?
                    """,
                    (
                        str(merged.get("name", "")),
                        str(merged.get("type", "mcp")),
                        str(merged.get("server", "")),
                        str(merged.get("status", "disconnected")),
                        connector_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_connector(connector_id)

    def delete_connector(self, connector_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM connectors WHERE id = ?", (connector_id,)
                )
                conn.execute(
                    "DELETE FROM mailbox_connectors WHERE connector_id = ?",
                    (connector_id,),
                )
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]

    def list_mailbox_connectors(self, mailbox_id: int) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT c.*, mc.enabled AS mailbox_enabled,
                           mc.allowed_tools AS allowed_tools
                    FROM connectors c
                    JOIN mailbox_connectors mc ON mc.connector_id = c.id
                    WHERE mc.mailbox_id = ?
                    ORDER BY c.id
                    """,
                    (mailbox_id,),
                ).fetchall()
            finally:
                conn.close()
        connectors = []
        for row in rows:
            connector = dict(row)
            connector["type"] = connector.get("type") or "mcp"
            connector["status"] = connector.get("status") or "disconnected"
            connector["enabled"] = bool(connector.get("mailbox_enabled"))
            connector["allowed_tools"] = connector.get("allowed_tools") or ""
            connector.pop("mailbox_enabled", None)
            connectors.append(connector)
        return connectors

    def assign_connector(
        self, mailbox_id: int, connector_id: int, data: dict[str, Any]
    ) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO mailbox_connectors
                        (mailbox_id, connector_id, enabled, allowed_tools)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(mailbox_id, connector_id) DO UPDATE SET
                        enabled = excluded.enabled,
                        allowed_tools = excluded.allowed_tools
                    """,
                    (
                        mailbox_id,
                        connector_id,
                        1 if data.get("enabled", True) else 0,
                        str(data.get("allowed_tools", "")),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return True

    def unassign_connector(self, mailbox_id: int, connector_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM mailbox_connectors WHERE mailbox_id = ? AND connector_id = ?",
                    (mailbox_id, connector_id),
                )
                conn.commit()
            finally:
                conn.close()
        return cur.rowcount > 0  # type: ignore[possibly-undefined]

    # ---- connector tool permissions ----

    def list_tool_permissions(
        self, mailbox_id: int, connector_id: int
    ) -> dict[str, dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM connector_tool_permissions "
                    "WHERE mailbox_id = ? AND connector_id = ?",
                    (mailbox_id, connector_id),
                ).fetchall()
            finally:
                conn.close()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            item["enabled"] = bool(item.get("enabled"))
            result[item["tool_name"]] = item
        return result

    def set_tool_permissions(
        self,
        mailbox_id: int,
        connector_id: int,
        permissions: dict[str, dict[str, Any]],
    ) -> None:
        """Upsert tool permissions for a connector. Unknown tools default deny."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                for tool_name, data in permissions.items():
                    conn.execute(
                        """
                        INSERT INTO connector_tool_permissions
                            (mailbox_id, connector_id, tool_name, enabled,
                             permission_level, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(mailbox_id, connector_id, tool_name) DO UPDATE SET
                            enabled = excluded.enabled,
                            permission_level = excluded.permission_level,
                            updated_at = excluded.updated_at
                        """,
                        (
                            mailbox_id,
                            connector_id,
                            str(tool_name),
                            1 if data.get("enabled") else 0,
                            str(data.get("permission_level", "read")),
                            now,
                            now,
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    # ---- discovered connector tools ----

    def replace_connector_tools(
        self, connector_id: int, tools: list[dict[str, Any]]
    ) -> None:
        """Persist discovered tools for a connector (replace previous set)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM connector_tools WHERE connector_id = ?",
                    (connector_id,),
                )
                for tool in tools:
                    conn.execute(
                        """
                        INSERT INTO connector_tools
                            (connector_id, name, title, description,
                             input_schema_json, output_schema_json,
                             annotations_json, enabled, risk_level,
                             discovered_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            connector_id,
                            str(tool.get("name", "")),
                            str(tool.get("title", "")),
                            str(tool.get("description", "")),
                            json.dumps(tool.get("input_schema") or {}),
                            json.dumps(tool.get("output_schema") or {}),
                            json.dumps(tool.get("annotations") or {}),
                            0,
                            str(tool.get("risk_level", "read")),
                            now,
                            now,
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    def list_connector_tools(self, connector_id: int) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM connector_tools WHERE connector_id = ? ORDER BY id",
                    (connector_id,),
                ).fetchall()
            finally:
                conn.close()
        tools = []
        for row in rows:
            tool = dict(row)
            tool["input_schema"] = json.loads(tool.get("input_schema_json") or "{}")
            tool["output_schema"] = json.loads(tool.get("output_schema_json") or "{}")
            tool["annotations"] = json.loads(tool.get("annotations_json") or "{}")
            tool["enabled"] = bool(tool.get("enabled"))
            tools.append(tool)
        return tools
