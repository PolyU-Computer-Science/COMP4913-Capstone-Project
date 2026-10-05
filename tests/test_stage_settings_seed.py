"""Seed-once behavior for built-in stage defaults."""

from __future__ import annotations

from email_assistant.core.settings_store import SettingsStore
from email_assistant.core.stage_seeds import (
    DRAFT_DEFAULTS,
    DRAFT_DEFAULTS_V1,
    STAGE_SEED_VERSION,
)


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


def _seed_v1_database(store: SettingsStore, prompt: str | None) -> None:
    """Simulate a v1-seeded database (no stage_seed_version row)."""
    import sqlite3

    store.ensure_default_stage_settings()
    # Force the stored version back to v1 and install the given prompt.
    conn = sqlite3.connect(store._db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) "
            "VALUES ('stage_seed_version', '1')"
        )
        conn.execute("DELETE FROM settings WHERE key = 'stage.draft.prompt'")
        if prompt is not None:
            conn.execute(
                "INSERT INTO settings (key, value) "
                "VALUES ('stage.draft.prompt', ?)",
                (prompt,),
            )
        conn.commit()
    finally:
        conn.close()


def test_fresh_db_receives_v2_prompt_with_classification(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)

    store = SettingsStore()
    store.ensure_default_stage_settings()

    draft = store.get_stage_settings("draft")
    assert "{classification}" in draft["prompt"]

    version = int(
        sqlite3_read_setting(store, "stage_seed_version") or "0"
    )
    assert version == STAGE_SEED_VERSION


def test_old_official_default_migrates_to_v2(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)

    store = SettingsStore()
    _seed_v1_database(store, DRAFT_DEFAULTS_V1["prompt"])

    warnings = store.migrate_stage_seeds()

    assert warnings == []
    migrated = store.get_stage_settings("draft")
    assert "{classification}" in migrated["prompt"]
    assert migrated["prompt"] == DRAFT_DEFAULTS["prompt"]
    assert (
        int(sqlite3_read_setting(store, "stage_seed_version") or "0")
        == STAGE_SEED_VERSION
    )


def test_customized_prompt_is_never_overwritten(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)

    store = SettingsStore()
    custom = DRAFT_DEFAULTS_V1["prompt"].replace(
        "Reply rules:", "My custom rules (user-edited):"
    )
    _seed_v1_database(store, custom)

    warnings = store.migrate_stage_seeds()

    # The custom prompt is preserved and a warning is surfaced for the UI.
    preserved = store.get_stage_settings("draft")
    assert "My custom rules (user-edited):" in preserved["prompt"]
    assert "{classification}" not in preserved["prompt"]
    assert len(warnings) == 1
    assert "{classification}" in warnings[0]

    # The version is still bumped so the migration does not re-run.
    assert (
        int(sqlite3_read_setting(store, "stage_seed_version") or "0")
        == STAGE_SEED_VERSION
    )


def sqlite3_read_setting(store: SettingsStore, key: str) -> str | None:
    import sqlite3

    conn = sqlite3.connect(store._db_path)
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None
