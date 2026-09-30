from __future__ import annotations

import pytest

from email_assistant.core.email_fetcher import (
    EmailSettings,
    fetch_emails,
    fetch_via_imap,
)


class _FakeMailBox:
    """Records fetch calls so tests can assert the IMAP query."""

    last_fetch_args: tuple | None = None
    last_fetch_kwargs: dict | None = None

    def __init__(self, server: str, port: int) -> None:
        self.server = server
        self.port = port

    def login(self, address: str, password: str, initial_folder: str):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:  # noqa: ANN002
        return False

    def fetch(self, *args, **kwargs):  # noqa: ANN001, ANN003
        _FakeMailBox.last_fetch_args = args
        _FakeMailBox.last_fetch_kwargs = kwargs
        return []


def _imap_settings() -> EmailSettings:
    return EmailSettings(
        enabled=True,
        server="imap.gmail.com",
        port=993,
        address="a@b.com",
        password="pw",
    )


def test_fetch_emails_returns_empty_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "email_assistant.core.email_fetcher.load_email_settings",
        lambda: EmailSettings(enabled=False),
    )

    assert fetch_emails() == []


def test_fetch_emails_returns_empty_when_imap_has_no_mail(monkeypatch) -> None:
    monkeypatch.setattr(
        "email_assistant.core.email_fetcher.load_email_settings",
        _imap_settings,
    )
    monkeypatch.setattr(
        "email_assistant.core.email_fetcher.fetch_via_imap",
        lambda settings: [],
    )

    assert fetch_emails() == []


def test_fetch_emails_raises_on_imap_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "email_assistant.core.email_fetcher.load_email_settings",
        _imap_settings,
    )

    def boom(settings: EmailSettings) -> list:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(
        "email_assistant.core.email_fetcher.fetch_via_imap",
        boom,
    )

    with pytest.raises(RuntimeError, match="connection refused"):
        fetch_emails()


def test_fetch_via_imap_fetches_all_emails(monkeypatch) -> None:
    """Default fetch includes read + unread (no UNSEEN criteria)."""
    monkeypatch.setattr(
        "email_assistant.core.email_fetcher.MailBox", _FakeMailBox
    )

    fetch_via_imap(_imap_settings())

    # No criteria argument = IMAP ALL (read + unread), only a limit.
    assert _FakeMailBox.last_fetch_args == ()
    assert _FakeMailBox.last_fetch_kwargs == {"limit": 50, "reverse": True}


def test_fetch_via_imap_respects_max_emails(monkeypatch) -> None:
    monkeypatch.setattr(
        "email_assistant.core.email_fetcher.MailBox", _FakeMailBox
    )

    fetch_via_imap(EmailSettings(enabled=True, address="a@b.com", max_emails=7))

    assert _FakeMailBox.last_fetch_kwargs == {"limit": 7, "reverse": True}


def test_env_folder_is_fixed_to_inbox() -> None:
    settings = EmailSettings.from_env({"EMAIL_FOLDER": "Some/Folder"})
    assert settings.folder == "INBOX"
