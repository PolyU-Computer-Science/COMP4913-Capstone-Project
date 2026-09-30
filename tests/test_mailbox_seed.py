"""Seed-once behavior for the built-in default mailbox."""

from __future__ import annotations

from email_assistant.core.settings_store import SettingsStore


def test_seeds_mailbox_topics_fields_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

    store = SettingsStore()

    assert store.ensure_default_mailbox() is True

    mailboxes = store.list_mailboxes()
    assert len(mailboxes) == 1
    mailbox = mailboxes[0]
    assert mailbox["address"] == "chiwacheng1231@gmail.com"
    assert mailbox["imap_host"] == "imap.gmail.com"
    assert mailbox["auto_process"] is True
    # Password is never seeded.
    assert not mailbox.get("password")
    assert store.get_mailbox_password(int(mailbox["id"])) in (None, "")

    topics = store.list_topics(int(mailbox["id"]))
    assert len(topics) >= 5
    names = {t["name"] for t in topics}
    assert "Career & Internship" in names

    fields = store.list_custom_fields(int(mailbox["id"]))
    assert len(fields) >= 3
    field_names = {f["name"] for f in fields}
    assert "Deadline" in field_names
    select_fields = [f for f in fields if f["type"] == "select"]
    assert select_fields and select_fields[0]["options"]

    # Second call is a no-op.
    assert store.ensure_default_mailbox() is False

    # User mailboxes block re-seeding entirely.
    store.create_mailbox({"name": "Other", "address": "other@x.com"})
    assert store.ensure_default_mailbox() is False


def test_seeds_password_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("EMAIL_PASSWORD", "secret-app-password")

    store = SettingsStore()
    assert store.ensure_default_mailbox() is True

    mailbox = store.list_mailboxes()[0]
    assert store.get_mailbox_password(int(mailbox["id"])) == "secret-app-password"
