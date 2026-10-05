"""Processed cases endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas import (
    CaseFieldOut,
    CaseOut,
    CasesResponse,
    DraftIn,
)
from backend.app.store import store

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("", response_model=CasesResponse)
def list_cases(
    mailbox_id: int | None = Query(default=None),
) -> CasesResponse:
    """Return processed cases (newest first), optionally mailbox-scoped."""
    cases = store.get_cases(mailbox_id)
    return CasesResponse(cases=cases, count=len(cases))


@router.patch("/{case_id}", response_model=CaseOut)
def update_case_draft(case_id: str, payload: DraftIn) -> CaseOut:
    """Update the draft reply of a processed case."""
    case = store.save_draft(case_id, payload.draft)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("/{case_id}/send", response_model=CaseOut)
def send_case(case_id: str) -> CaseOut:
    """Send the approved draft via SMTP and mark the case as sent."""
    from email_assistant.core.email_sender import send_reply
    from email_assistant.core.settings_store import SettingsStore

    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.draft.strip():
        raise HTTPException(status_code=422, detail="Draft is empty")

    account = SettingsStore().get_mailbox_send_account(case.mailbox_id)
    if account is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "The case's mailbox has no SMTP account configured; "
                "cannot send from the correct mailbox"
            ),
        )

    from email_assistant.core.observability import Observer

    observer = Observer()
    try:
        with observer.run(
            stage="send",
            mailbox_id=case.mailbox_id,
            email_id=case.id,
            case_id=case.id,
        ):
            send_reply(
                account,
                to=case.email.sender,
                subject=case.email.subject,
                body=case.draft,
            )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001 - report SMTP failures to the UI
        raise HTTPException(status_code=502, detail=f"SMTP error: {error}") from error

    sent = store.mark_sent(case_id)
    if sent is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return sent


# ---- case fields ----


@router.get("/{case_id}/fields", response_model=list[CaseFieldOut])
def get_case_fields(case_id: str) -> list[CaseFieldOut]:
    """Return the case's mailbox custom fields merged with saved values."""
    from email_assistant.core.mailbox_context import load_mailbox_context

    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    if case.mailbox_id is None:
        return []

    context = load_mailbox_context(case.mailbox_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    saved = store.get_case_field_values(case_id)

    result: list[CaseFieldOut] = []
    for field in context.active_fields:
        value_json = saved.get(int(field["id"]))
        value = json.loads(value_json) if value_json else None
        result.append(
            CaseFieldOut(
                field_id=int(field["id"]),
                key=str(field.get("name", "")).lower().replace(" ", "_"),
                name=str(field.get("name", "")),
                type=str(field.get("type", "text")),
                required=bool(field.get("required")),
                options=_parse_options(field.get("options")),
                value=value,
            )
        )
    return result


@router.put("/{case_id}/fields", response_model=list[CaseFieldOut])
def update_case_fields(case_id: str, payload: dict) -> list[CaseFieldOut]:
    """Bulk-update case field values with server-side validation.

    The payload is ``{"values": {"<field_id>": <value>, ...}}``.
    """
    from email_assistant.core.field_validation import validate_field_value
    from email_assistant.core.mailbox_context import load_mailbox_context

    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    if case.mailbox_id is None:
        raise HTTPException(status_code=400, detail="Case has no mailbox")

    context = load_mailbox_context(case.mailbox_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    values = payload.get("values", {}) if isinstance(payload, dict) else {}
    fields_by_id = {int(f["id"]): f for f in context.active_fields}

    # Reject any field id that does not belong to this mailbox.
    for field_id in values:
        if int(field_id) not in fields_by_id:
            raise HTTPException(
                status_code=400,
                detail=f"Field {field_id} does not belong to this mailbox",
            )

    # Validate each value against its field definition.
    for field_id, value in values.items():
        field = fields_by_id[int(field_id)]
        ok, error = validate_field_value(field, value)
        if not ok:
            raise HTTPException(status_code=422, detail=error)

    store.set_case_field_values(
        case_id, {int(k): json.dumps(v) for k, v in values.items()}
    )

    return get_case_fields(case_id)


def _parse_options(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [opt.strip() for opt in str(raw).split(",") if opt.strip()]
