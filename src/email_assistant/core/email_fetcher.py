from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Self

from dotenv import load_dotenv
from imap_tools import MailBox, MailMessage
import os


def format_email(email: dict[str, str]) -> str:
    """Render a structured email dict into a plain-text block for the LLM."""
    return (
        f"From: {email['sender']}\n"
        f"Subject: {email['subject']}\n"
        f"Date: {email['timestamp']}\n"
        f"\n"
        f"{email['body']}"
    )


@dataclass(frozen=True)
class EmailSettings:
    """Configuration for IMAP email fetching."""

    enabled: bool = False
    server: str = "imap.gmail.com"
    port: int = 993
    address: str = ""
    password: str = ""
    folder: str = "INBOX"
    max_emails: int = 50

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        if env is None:
            load_dotenv(override=False)
            source: Mapping[str, str] = os.environ
        else:
            source = env

        enabled = _get_str(source, "EMAIL_ENABLED", "false").lower() in ("true", "1", "yes")
        address = _get_str(source, "EMAIL_ADDRESS", "").strip()
        password = _get_str(source, "EMAIL_PASSWORD", "").strip()

        if enabled and not address:
            print("WARNING: EMAIL_ENABLED=true but EMAIL_ADDRESS is not set.")
            enabled = False

        if enabled and not password:
            print("WARNING: EMAIL_ENABLED=true but EMAIL_PASSWORD is not set.")
            enabled = False

        max_emails = 50
        raw_max = _get_str(source, "EMAIL_MAX_EMAILS", "50").strip()
        try:
            max_emails = int(raw_max)
            if max_emails < 1:
                max_emails = 50
        except ValueError:
            pass

        return cls(
            enabled=enabled,
            server=_get_str(source, "EMAIL_SERVER", "imap.gmail.com"),
            port=int(_get_str(source, "EMAIL_PORT", "993")),
            address=address,
            password=password,
            folder="INBOX",
            max_emails=max_emails,
        )


def _get_str(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped or default


def _convert_message(msg: MailMessage) -> dict:
    """Convert an imap_tools MailMessage to the internal email dict format."""
    from_dt = msg.date
    if from_dt:
        if from_dt.tzinfo is None:
            from_dt = from_dt.replace(tzinfo=timezone.utc)
        timestamp = from_dt.isoformat()
    else:
        timestamp = datetime.now(timezone.utc).isoformat()

    inline_attachments = []
    for att in msg.attachments:
        cid = (att.content_id or "").strip().strip("<>").strip()
        if cid and (att.content_type or "").startswith("image/"):
            inline_attachments.append(
                {
                    "cid": cid,
                    "content_type": att.content_type,
                    "filename": att.filename or "",
                    "data": att.payload,
                }
            )

    return {
        "sender": msg.from_,
        "subject": msg.subject or "(no subject)",
        "body": msg.text or msg.html or "",
        "html": msg.html or "",
        "timestamp": timestamp,
        "attachments": inline_attachments,
    }


def fetch_via_imap(settings: EmailSettings) -> list[dict[str, str]]:
    """Fetch all emails (read + unread) from the IMAP server."""
    print(f"Connecting to IMAP server: {settings.server}:{settings.port}")
    print(f"Fetching all emails from folder: {settings.folder}")

    with MailBox(settings.server, port=settings.port).login(
        settings.address,
        settings.password,
        initial_folder=settings.folder,
    ) as mailbox:
        # No criteria = IMAP ALL (read + unread); reverse=True = newest first.
        messages = list(mailbox.fetch(limit=settings.max_emails, reverse=True))

        if not messages:
            print("No emails found.")
            return []

        print(f"Found {len(messages)} email(s) (newest first).")

        emails = []
        for msg in messages:
            email = _convert_message(msg)
            emails.append(email)

        return emails


def load_email_settings() -> EmailSettings:
    """Resolve email settings, preferring an enabled DB mail account over env."""
    from email_assistant.core.settings_store import SettingsStore

    account = SettingsStore().get_enabled_mail_account()
    if account is None:
        return EmailSettings.from_env()

    return EmailSettings(
        enabled=True,
        server=str(account.get("imap_host") or "imap.gmail.com"),
        port=int(account.get("imap_port") or 993),
        address=str(account.get("address") or ""),
        password=str(account.get("password") or ""),
        folder="INBOX",
        max_emails=int(account.get("max_emails") or 50),
    )


def fetch_emails(mailbox_id: int | None = None) -> list[dict[str, str]]:
    """Fetch emails from the inbox via IMAP.

    If ``mailbox_id`` is provided, emails are fetched from that mailbox's IMAP
    configuration and tagged with the mailbox id at ingestion. Otherwise the
    legacy behaviour is used: an enabled mail account (settings DB) or
    ``EMAIL_ENABLED`` env with valid credentials, with no mailbox scoping.
    """
    if mailbox_id is not None:
        return _fetch_mailbox_emails(mailbox_id)

    settings = load_email_settings()

    if settings.enabled and settings.address:
        return fetch_via_imap(settings)

    print("No enabled mail account; no emails to fetch.")
    return []


def _fetch_mailbox_emails(mailbox_id: int) -> list[dict[str, str]]:
    """Fetch emails for a specific mailbox and tag them with ``mailbox_id``."""
    from email_assistant.core.settings_store import SettingsStore

    store = SettingsStore()
    mailbox = store.get_mailbox(mailbox_id)
    if mailbox is None:
        print(f"Mailbox {mailbox_id} not found; no emails to fetch.")
        return []

    password = store.get_mailbox_password(mailbox_id) or ""
    settings = EmailSettings(
        enabled=True,
        server=str(mailbox.get("imap_host") or "imap.gmail.com"),
        port=int(mailbox.get("imap_port") or 993),
        address=str(mailbox.get("address") or ""),
        password=password,
        folder=str(mailbox.get("imap_folder") or "INBOX"),
        max_emails=int(mailbox.get("max_emails") or 50),
    )

    if not settings.address or not settings.server:
        print(f"Mailbox {mailbox_id} has no address/IMAP host; skipping.")
        return []

    emails = fetch_via_imap(settings)
    for email in emails:
        email["mailbox_id"] = mailbox_id
    return emails
