"""Mailbox business-context endpoints.

A mailbox groups email connection, AI behaviour, topics, custom fields,
knowledge sources and connectors into a single business context.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from email_assistant.core.settings_store import SettingsStore

from backend.app.schemas import (
    ConnectorAssignmentIn,
    ConnectorIn,
    ConnectorOut,
    CustomFieldIn,
    CustomFieldOut,
    KnowledgeSourceIn,
    KnowledgeSourceOut,
    MailboxConnectorOut,
    MailboxIn,
    MailboxOut,
    TestResult,
    TopicIn,
    TopicOut,
)

router = APIRouter(prefix="/api/mailboxes", tags=["mailboxes"])


def _store() -> SettingsStore:
    return SettingsStore()


def _mailbox_out(data: dict) -> MailboxOut:
    mailbox_id = data.get("id")
    has_password = bool(
        mailbox_id is not None and _store().get_mailbox_password(int(mailbox_id))
    )
    return MailboxOut(**{**data, "has_password": has_password})


def _require_mailbox(mailbox_id: int) -> None:
    if _store().get_mailbox(mailbox_id) is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")


# ---- mailboxes ----

@router.get("", response_model=list[MailboxOut])
def list_mailboxes(
    include_system: bool = False,
) -> list[MailboxOut]:
    """List mailboxes. System mailboxes (e.g. Legacy) are hidden by default."""
    return [_mailbox_out(m) for m in _store().list_mailboxes(include_system=include_system)]


@router.post("", response_model=MailboxOut, status_code=201)
def create_mailbox(payload: MailboxIn) -> MailboxOut:
    data = payload.model_dump()
    password = str(data.pop("password", "") or "")
    mailbox = _store().create_mailbox(data)
    if password:
        _store().set_mailbox_password(mailbox["id"], password)
    return _mailbox_out(mailbox)


# ---- knowledge sources (static paths before {mailbox_id}) ----

@router.get("/knowledge", response_model=list[KnowledgeSourceOut])
def list_knowledge_sources() -> list[KnowledgeSourceOut]:
    return [KnowledgeSourceOut(**s) for s in _store().list_knowledge_sources()]


@router.post("/knowledge", response_model=KnowledgeSourceOut, status_code=201)
def create_knowledge_source(payload: KnowledgeSourceIn) -> KnowledgeSourceOut:
    return KnowledgeSourceOut(**_store().create_knowledge_source(payload.model_dump()))


@router.put("/knowledge/{source_id}", response_model=KnowledgeSourceOut)
def update_knowledge_source(
    source_id: int, payload: KnowledgeSourceIn
) -> KnowledgeSourceOut:
    source = _store().update_knowledge_source(source_id, payload.model_dump())
    if source is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return KnowledgeSourceOut(**source)


@router.delete("/knowledge/{source_id}")
def delete_knowledge_source(source_id: int) -> dict:
    if not _store().delete_knowledge_source(source_id):
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    return {"ok": True}


# ---- connectors (static paths before {mailbox_id}) ----

@router.get("/connectors", response_model=list[ConnectorOut])
def list_connectors() -> list[ConnectorOut]:
    return [ConnectorOut(**c) for c in _store().list_connectors()]


@router.post("/connectors", response_model=ConnectorOut, status_code=201)
def create_connector(payload: ConnectorIn) -> ConnectorOut:
    return ConnectorOut(**_store().create_connector(payload.model_dump()))


@router.put("/connectors/{connector_id}", response_model=ConnectorOut)
def update_connector(connector_id: int, payload: ConnectorIn) -> ConnectorOut:
    connector = _store().update_connector(connector_id, payload.model_dump())
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return ConnectorOut(**connector)


@router.delete("/connectors/{connector_id}")
def delete_connector(connector_id: int) -> dict:
    if not _store().delete_connector(connector_id):
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"ok": True}


# ---- mailbox detail ----

@router.get("/{mailbox_id}", response_model=MailboxOut)
def get_mailbox(mailbox_id: int) -> MailboxOut:
    mailbox = _store().get_mailbox(mailbox_id)
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    return _mailbox_out(mailbox)


@router.put("/{mailbox_id}", response_model=MailboxOut)
def update_mailbox(mailbox_id: int, payload: MailboxIn) -> MailboxOut:
    data = payload.model_dump()
    password = str(data.pop("password", "") or "")
    mailbox = _store().update_mailbox(mailbox_id, data)
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    if password:
        _store().set_mailbox_password(mailbox_id, password)
    return _mailbox_out(mailbox)


@router.delete("/{mailbox_id}")
def delete_mailbox(mailbox_id: int) -> dict:
    if not _store().delete_mailbox(mailbox_id):
        raise HTTPException(status_code=404, detail="Mailbox not found")
    return {"ok": True}


@router.post("/{mailbox_id}/test", response_model=TestResult)
def test_mailbox(mailbox_id: int) -> TestResult:
    """Test the mailbox's IMAP connection (login + folder select only)."""
    from email_assistant.core.email_fetcher import EmailSettings
    from imap_tools import MailBox

    mailbox = _store().get_mailbox(mailbox_id)
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    if not mailbox.get("address") or not mailbox.get("imap_host"):
        return TestResult(
            ok=False, message="Email address or IMAP server is not configured."
        )

    password = _store().get_mailbox_password(mailbox_id) or ""
    if not password:
        return TestResult(
            ok=False,
            message="No password set. Enter your IMAP password (for Gmail, "
            "an App Password) and save before testing.",
        )

    server = str(mailbox.get("imap_host") or "")
    port = int(mailbox.get("imap_port") or 993)
    folder = str(mailbox.get("imap_folder") or "INBOX")

    try:
        with MailBox(server, port=port).login(
            str(mailbox.get("address") or ""),
            password,
            initial_folder=folder,
        ) as imap:
            imap.client.noop()
        return TestResult(
            ok=True,
            message=f"IMAP connection to {server}:{port} ({folder}) successful",
        )
    except Exception as error:  # noqa: BLE001 - surface to the UI
        raw = str(error)
        lowered = raw.lower()
        if "empty username or password" in lowered or "authenticationfailed" in lowered:
            return TestResult(
                ok=False,
                message="Authentication failed. Check the email address and "
                "password (for Gmail, use a 16-character App Password).",
            )
        if "name or service not known" in lowered or "getaddrinfo" in lowered:
            return TestResult(
                ok=False,
                message=f"Cannot reach IMAP server '{server}'. "
                "Check the server name and your network.",
            )
        if "timed out" in lowered:
            return TestResult(
                ok=False,
                message=f"Connection to '{server}' timed out.",
            )
        return TestResult(ok=False, message=raw)


# ---- topics ----

@router.get("/{mailbox_id}/topics", response_model=list[TopicOut])
def list_topics(mailbox_id: int) -> list[TopicOut]:
    _require_mailbox(mailbox_id)
    return [TopicOut(**t) for t in _store().list_topics(mailbox_id)]


@router.post("/{mailbox_id}/topics", response_model=TopicOut, status_code=201)
def create_topic(mailbox_id: int, payload: TopicIn) -> TopicOut:
    _require_mailbox(mailbox_id)
    return TopicOut(**(_store().create_topic(mailbox_id, payload.model_dump())))


@router.put("/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: int, payload: TopicIn) -> TopicOut:
    topic = _store().update_topic(topic_id, payload.model_dump())
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return TopicOut(**topic)


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int) -> dict:
    if not _store().delete_topic(topic_id):
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"ok": True}


# ---- custom fields ----

@router.get("/{mailbox_id}/fields", response_model=list[CustomFieldOut])
def list_custom_fields(mailbox_id: int) -> list[CustomFieldOut]:
    _require_mailbox(mailbox_id)
    return [CustomFieldOut(**f) for f in _store().list_custom_fields(mailbox_id)]


@router.post("/{mailbox_id}/fields", response_model=CustomFieldOut, status_code=201)
def create_custom_field(mailbox_id: int, payload: CustomFieldIn) -> CustomFieldOut:
    _require_mailbox(mailbox_id)
    return CustomFieldOut(**_store().create_custom_field(mailbox_id, payload.model_dump()))


@router.put("/fields/{field_id}", response_model=CustomFieldOut)
def update_custom_field(field_id: int, payload: CustomFieldIn) -> CustomFieldOut:
    field = _store().update_custom_field(field_id, payload.model_dump())
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")
    return CustomFieldOut(**field)


@router.delete("/fields/{field_id}")
def delete_custom_field(field_id: int) -> dict:
    if not _store().delete_custom_field(field_id):
        raise HTTPException(status_code=404, detail="Field not found")
    return {"ok": True}


# ---- mailbox knowledge assignment ----

@router.get("/{mailbox_id}/knowledge", response_model=list[KnowledgeSourceOut])
def list_mailbox_knowledge(mailbox_id: int) -> list[KnowledgeSourceOut]:
    _require_mailbox(mailbox_id)
    return [KnowledgeSourceOut(**s) for s in _store().list_mailbox_knowledge(mailbox_id)]


@router.post("/{mailbox_id}/knowledge/{source_id}")
def assign_knowledge(mailbox_id: int, source_id: int) -> dict:
    _require_mailbox(mailbox_id)
    if _store().get_knowledge_source(source_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    _store().assign_knowledge(mailbox_id, source_id)
    return {"ok": True}


@router.delete("/{mailbox_id}/knowledge/{source_id}")
def unassign_knowledge(mailbox_id: int, source_id: int) -> dict:
    _require_mailbox(mailbox_id)
    _store().unassign_knowledge(mailbox_id, source_id)
    return {"ok": True}


# ---- mailbox connector assignment ----

@router.get("/{mailbox_id}/connectors", response_model=list[MailboxConnectorOut])
def list_mailbox_connectors(mailbox_id: int) -> list[MailboxConnectorOut]:
    _require_mailbox(mailbox_id)
    return [
        MailboxConnectorOut(**c) for c in _store().list_mailbox_connectors(mailbox_id)
    ]


@router.put("/{mailbox_id}/connectors/{connector_id}")
def assign_connector(
    mailbox_id: int, connector_id: int, payload: ConnectorAssignmentIn
) -> dict:
    _require_mailbox(mailbox_id)
    if _store().get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    _store().assign_connector(mailbox_id, connector_id, payload.model_dump())
    return {"ok": True}


@router.delete("/{mailbox_id}/connectors/{connector_id}")
def unassign_connector(mailbox_id: int, connector_id: int) -> dict:
    _require_mailbox(mailbox_id)
    _store().unassign_connector(mailbox_id, connector_id)
    return {"ok": True}
