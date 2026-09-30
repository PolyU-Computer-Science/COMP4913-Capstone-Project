"""Observability endpoints: processing traces and stats."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from email_assistant.core.observability_store import ObservabilityStore
from email_assistant.core.settings_store import SettingsStore

from backend.app.schemas import ProcessingRunOut

router = APIRouter(prefix="/api/mailboxes", tags=["observability"])


def _run_out(run: dict) -> ProcessingRunOut:
    return ProcessingRunOut(
        id=run["id"],
        trace_id=run["trace_id"],
        mailbox_id=run["mailbox_id"],
        email_id=run["email_id"],
        case_id=run["case_id"],
        stage=run["stage"],
        status=run["status"],
        provider=run["provider"],
        model=run["model"],
        started_at=run["started_at"],
        completed_at=run["completed_at"],
        latency_ms=run["latency_ms"],
        input_tokens=run["input_tokens"],
        output_tokens=run["output_tokens"],
        total_tokens=run["total_tokens"],
        metadata=_parse_json(run.get("metadata_json")),
        error_type=run["error_type"],
        error_message=run["error_message"],
    )


# One email's pipeline = its runs share a trace_id, ordered by id (time).
@router.get("/{mailbox_id}/processing-traces")
def list_processing_traces(
    mailbox_id: int,
    limit: int = Query(default=50),
) -> list[dict]:
    """Return recent processing runs grouped into per-email traces."""
    if SettingsStore().get_mailbox(mailbox_id) is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    store = ObservabilityStore()
    runs = store.list_runs(mailbox_id=mailbox_id, limit=500)

    # Sync-level fetch runs carry no email id and would render as
    # "(unknown email)" — per-email pipelines start at processing.
    runs = [r for r in runs if r["stage"] != "email_fetch"]

    traces: dict[str, list[dict]] = {}
    order: list[str] = []
    for run in runs:
        trace_id = run.get("trace_id") or f"fetch-{run['id']}"
        if trace_id not in traces:
            traces[trace_id] = []
            order.append(trace_id)
        traces[trace_id].append(run)

    result = []
    for trace_id in order[:limit]:
        trace_runs = sorted(traces[trace_id], key=lambda r: r["id"])
        email_id = next((r["email_id"] for r in trace_runs if r["email_id"]), None)
        email_subject = (
            store.get_email_subject(email_id) if email_id else None
        )
        returnable = [_run_out(r) for r in trace_runs]
        result.append(
            {
                "trace_id": trace_id,
                "email_id": email_id,
                "email_subject": email_subject,
                "status": (
                    "failed"
                    if any(r["status"] == "failed" for r in trace_runs)
                    else "success"
                ),
                "total_latency_ms": sum(
                    r["latency_ms"] or 0 for r in trace_runs
                ),
                "total_tokens": sum(r["total_tokens"] or 0 for r in trace_runs),
                "model": next(
                    (r["model"] for r in trace_runs if r["model"]), None
                ),
                "started_at": trace_runs[0]["started_at"],
                "runs": returnable,
            }
        )
    return result


@router.get("/{mailbox_id}/processing-runs", response_model=list[ProcessingRunOut])
def list_processing_runs(
    mailbox_id: int,
    email_id: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    limit: int = Query(default=100),
) -> list[ProcessingRunOut]:
    if SettingsStore().get_mailbox(mailbox_id) is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    runs = ObservabilityStore().list_runs(
        mailbox_id=mailbox_id, email_id=email_id, stage=stage, limit=limit
    )
    return [_run_out(r) for r in runs]


@router.get("/{mailbox_id}/processing-stats", response_model=dict)
def processing_stats(mailbox_id: int) -> dict:
    if SettingsStore().get_mailbox(mailbox_id) is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    store = ObservabilityStore()
    runs = store.list_runs(mailbox_id=mailbox_id, limit=10000)

    # "Processed" counts emails, not runs: group by trace, one per email.
    # email_fetch runs are excluded — they belong to sync operations, not
    # to processing a specific email.
    _NON_EMAIL_STAGES = {"email_fetch"}
    processing = [r for r in runs if r["stage"] not in _NON_EMAIL_STAGES]
    # Runs without a trace_id (e.g. ad-hoc classification calls) each count
    # as one unit; runs sharing a trace_id count once per email.
    traces: set[str] = set()
    untraced = 0
    for r in processing:
        if r.get("trace_id"):
            traces.add(r["trace_id"])
        else:
            untraced += 1
    processed = len(traces) + untraced

    failed_traces: set[str] = set()
    failed_untraced = 0
    for r in runs:
        if r["status"] != "failed":
            continue
        if r.get("trace_id"):
            failed_traces.add(r["trace_id"])
        else:
            failed_untraced += 1
    failed = len(failed_traces & traces) + min(failed_untraced, untraced)

    latencies = [r["latency_ms"] for r in processing if r["latency_ms"] is not None]
    tokens = sum(r["total_tokens"] or 0 for r in processing)

    return {
        "processed": processed,
        "success_rate": round((processed - failed) / processed, 4)
        if processed
        else 0.0,
        "average_latency_ms": round(sum(latencies) / len(latencies), 1)
        if latencies
        else 0.0,
        "total_tokens": tokens,
    }


def _parse_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
