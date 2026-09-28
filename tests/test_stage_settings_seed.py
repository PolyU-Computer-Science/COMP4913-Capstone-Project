"""Seed-once behavior for built-in stage defaults."""

from __future__ import annotations

from email_assistant.core.settings_store import SettingsStore


def test_seeds_once_and_never_overwrites(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)

    store = SettingsStore()

    assert store.ensure_default_stage_settings() is True
    classification = store.get_stage_settings("classification")
    assert classification["role"] == "Email Classifier"
    assert "{email_content}" in classification["prompt"]
    assert "{available_topics}" in classification["prompt"]

    draft = store.get_stage_settings("draft")
    assert draft["role"] == "Reply Drafter"
    assert "{knowledge_context}" in draft["prompt"]

    # Second call is a no-op.
    assert store.ensure_default_stage_settings() is False

    # User edits are never overwritten.
    store.set_stage_settings("classification", {"role": "Custom"})
    assert store.ensure_default_stage_settings() is False
    assert store.get_stage_settings("classification")["role"] == "Custom"
