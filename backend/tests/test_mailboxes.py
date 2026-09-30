"""Mailbox / topic / field / knowledge / connector API tests (hermetic)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from email_assistant.core.settings_store import SettingsStore

client = TestClient(app)


@pytest.fixture(autouse=True)
def _tmp_settings_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)
    yield tmp_path


def _mailbox(**overrides) -> dict:
    data = {"name": "Support", "address": "support@company.com"}
    data.update(overrides)
    return data


def test_mailbox_crud_roundtrip() -> None:
    created = client.post("/api/mailboxes", json=_mailbox(purpose="support"))
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Support"
    assert body["purpose"] == "support"
    mailbox_id = body["id"]

    listed = client.get("/api/mailboxes")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    updated = client.put(
        f"/api/mailboxes/{mailbox_id}", json=_mailbox(name="Support 2")
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Support 2"

    deleted = client.delete(f"/api/mailboxes/{mailbox_id}")
    assert deleted.status_code == 200
    assert client.get("/api/mailboxes").json() == []


def test_mailbox_password_not_leaked() -> None:
    created = client.post(
        "/api/mailboxes", json=_mailbox(password="secret-pass")
    )
    body = created.json()
    assert "password" not in body
    # The raw password must never be returned; only the has_password flag.
    assert body["has_password"] is True

    # A mailbox created without a password reports has_password=False.
    bare = client.post("/api/mailboxes", json=_mailbox()).json()
    assert bare["has_password"] is False


def test_mailbox_password_encrypted_at_rest(tmp_path) -> None:
    import sqlite3

    db = tmp_path / "settings.db"
    store = SettingsStore(db_path=str(db))
    mailbox = store.create_mailbox({"name": "Support"})
    store.set_mailbox_password(mailbox["id"], "super-secret")

    conn = sqlite3.connect(str(db))
    raw = conn.execute("SELECT password FROM mailboxes").fetchone()[0]
    conn.close()

    assert raw != "super-secret"
    assert store.get_mailbox_password(mailbox["id"]) == "super-secret"


def test_topic_crud() -> None:
    mailbox_id = client.post("/api/mailboxes", json=_mailbox()).json()["id"]

    created = client.post(
        f"/api/mailboxes/{mailbox_id}/topics",
        json={"name": "Password Reset", "description": "login issues"},
    )
    assert created.status_code == 201
    topic_id = created.json()["id"]

    listed = client.get(f"/api/mailboxes/{mailbox_id}/topics")
    assert len(listed.json()) == 1

    updated = client.put(
        f"/api/mailboxes/topics/{topic_id}",
        json={"name": "Password Reset", "description": "updated"},
    )
    assert updated.json()["description"] == "updated"

    deleted = client.delete(f"/api/mailboxes/topics/{topic_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/mailboxes/{mailbox_id}/topics").json() == []


def test_custom_field_crud() -> None:
    mailbox_id = client.post("/api/mailboxes", json=_mailbox()).json()["id"]

    created = client.post(
        f"/api/mailboxes/{mailbox_id}/fields",
        json={"name": "Customer ID", "type": "text", "required": True},
    )
    assert created.status_code == 201
    assert created.json()["required"] is True
    field_id = created.json()["id"]

    listed = client.get(f"/api/mailboxes/{mailbox_id}/fields")
    assert len(listed.json()) == 1

    deleted = client.delete(f"/api/mailboxes/fields/{field_id}")
    assert deleted.status_code == 200


def test_knowledge_source_crud_and_assignment() -> None:
    source = client.post(
        "/api/mailboxes/knowledge", json={"name": "Support FAQ", "type": "document"}
    )
    assert source.status_code == 201
    source_id = source.json()["id"]

    mailbox_id = client.post("/api/mailboxes", json=_mailbox()).json()["id"]

    assigned = client.post(f"/api/mailboxes/{mailbox_id}/knowledge/{source_id}")
    assert assigned.status_code == 200

    mailbox_knowledge = client.get(f"/api/mailboxes/{mailbox_id}/knowledge")
    assert len(mailbox_knowledge.json()) == 1
    assert mailbox_knowledge.json()[0]["name"] == "Support FAQ"

    unassigned = client.delete(f"/api/mailboxes/{mailbox_id}/knowledge/{source_id}")
    assert unassigned.status_code == 200
    assert client.get(f"/api/mailboxes/{mailbox_id}/knowledge").json() == []


def test_connector_crud_and_assignment() -> None:
    connector = client.post(
        "/api/mailboxes/connectors", json={"name": "GitHub", "type": "mcp"}
    )
    assert connector.status_code == 201
    connector_id = connector.json()["id"]

    mailbox_id = client.post("/api/mailboxes", json=_mailbox()).json()["id"]

    assigned = client.put(
        f"/api/mailboxes/{mailbox_id}/connectors/{connector_id}",
        json={"enabled": True, "allowed_tools": "read_files"},
    )
    assert assigned.status_code == 200

    mailbox_connectors = client.get(f"/api/mailboxes/{mailbox_id}/connectors")
    assert len(mailbox_connectors.json()) == 1
    entry = mailbox_connectors.json()[0]
    assert entry["enabled"] is True
    assert entry["allowed_tools"] == "read_files"


def test_mailbox_requires_existing_for_subresources() -> None:
    response = client.get("/api/mailboxes/99999/topics")
    assert response.status_code == 404
