"""Email fetching and processing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from email_assistant.core.observability import Observer
from email_assistant.core.settings_store import SettingsStore

from backend.app.schemas import (
    CaseOut,
    ClassificationOut,
    EmailsResponse,
    ProcessResponse,
    SyncResponse,
)
from backend.app.store import store

router = APIRouter(prefix="/api/emails", tags=["emails"])


class SyncIn(BaseModel):
    """Optional payload for sync — target a single mailbox, or all."""

    mailbox_id: int | None = None


@router.get("", response_model=EmailsResponse)
def list_emails(
    mailbox_id: int | None = Query(default=None),
) -> EmailsResponse:
    """Return stored emails, optionally scoped to a single mailbox."""
    emails = store.list_emails(mailbox_id)
    return EmailsResponse(emails=emails, count=len(emails))


@router.post("/sync", response_model=SyncResponse)
def sync_emails(payload: SyncIn | None = None) -> SyncResponse:
    """Fetch emails via IMAP and persist them (deduped).

    With ``mailbox_id``: sync that mailbox only. Without: sync every
    configured mailbox (the legacy unscoped env fallback no longer applies —
    emails always belong to a mailbox).
    """
    from email_assistant.core import fetch_emails

    mailbox_id = payload.mailbox_id if payload else None
    target_mailboxes: list[int]
    if mailbox_id is not None:
        target_mailboxes = [mailbox_id]
    else:
        target_mailboxes = [
            m["id"] for m in SettingsStore().list_mailboxes(include_system=False)
        ]

    observer = Observer()
    raw_emails: list[dict[str, str]] = []
    fetch_errors: list[str] = []
    for mb_id in target_mailboxes:
        try:
            with observer.run(stage="email_fetch", mailbox_id=mb_id):
                raw_emails.extend(fetch_emails(mb_id))
        except Exception as error:  # noqa: BLE001 - surface IMAP failures to the UI
            print(f"IMAP fetch failed for mailbox {mb_id}: {error}")
            fetch_errors.append(str(error))

    if fetch_errors and not raw_emails and len(target_mailboxes) == 1:
        raise HTTPException(status_code=502, detail=f"IMAP fetch failed: {fetch_errors[0]}")

    added, emails = store.sync_emails(raw_emails, mailbox_id)
    return SyncResponse(synced=added, emails=emails, count=len(emails))


@router.get("/{email_id}/attachments/{cid}")
def get_attachment(email_id: str, cid: str) -> Response:
    """Serve an inline email attachment (e.g. a ``cid:`` image)."""
    attachment = store.get_attachment(email_id, cid)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    content_type, data = attachment
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": "inline"},
    )


@router.post("/{email_id}/process", response_model=ProcessResponse)
def process_email(email_id: str) -> ProcessResponse:
    """Run the AI crew (classify + draft) on a stored email by id.

    The pipeline is mailbox-scoped: the mailbox's topics constrain the
    classifier, and its indexed knowledge grounds the drafter (RAG). Each
    stage is traced via the observer for latency/usage.
    """
    import uuid

    from email_assistant.agents import EmailAssistant
    from email_assistant.core import format_email
    from email_assistant.core.knowledge_retrieval import KnowledgeRetriever
    from email_assistant.core.mailbox_context import load_mailbox_context
    from email_assistant.core.rag import build_retrieval_query, format_knowledge_context

    email = store.get_email(email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    store.mark_processing(email_id)

    content = format_email(
        {
            "sender": email.sender,
            "subject": email.subject,
            "timestamp": email.timestamp,
            "body": email.body,
        }
    )

    # Load the mailbox's business context (topics, fields, knowledge, tools).
    context = load_mailbox_context(email.mailbox_id) if email.mailbox_id else None

    trace_id = uuid.uuid4().hex
    observer = Observer()

    # 1. Knowledge retrieval (mailbox-scoped RAG). Best-effort: a retrieval
    #    failure or zero results never blocks drafting.
    knowledge_context = ""
    knowledge_refs: list[dict] = []
    retrieval_stats: dict = {}
    if context and context.knowledge_sources and context.mailbox.get("use_knowledge"):
        try:
            with observer.run(
                stage="knowledge_retrieval",
                mailbox_id=email.mailbox_id,
                email_id=email_id,
                trace_id=trace_id,
            ) as retrieval_run_id:
                query = build_retrieval_query(
                    subject=email.subject,
                    body=email.body,
                )
                retriever = KnowledgeRetriever()
                results, stats = retriever.search_detailed(
                    email.mailbox_id, query, top_k=5
                )
                knowledge_context = format_knowledge_context(results)
                knowledge_refs = [
                    {
                        "chunk_id": r.chunk_id,
                        "source_id": r.source_id,
                        "score": r.score,
                    }
                    for r in results
                ]
                retrieval_stats = {
                    "query": query[:200],
                    "top_k": 5,
                    "chunks_considered": stats.chunks_considered,
                    "stale_chunks_skipped": stats.stale_chunks_skipped,
                    "returned_count": stats.returned_count,
                    "embedding_provider": retriever._embedding.provider,
                    "embedding_model": retriever._embedding.model,
                    "embedding_dim": retriever._embedding.dim,
                }
            observer.attach_metadata(retrieval_run_id, retrieval_stats)
        except Exception:  # noqa: BLE001 - RAG must not block processing
            knowledge_context = ""

    # 2. Classification via the structured runtime (same path as evaluation):
    #    raw response → JSON extraction → repair → Pydantic validation
    #    → business validation (topic resolution + field validation).
    from email_assistant.core.structured_classification import StructuredClassifier
    from email_assistant.core.structured_llm import (
        StructuredLLMError,
        build_structured_client_from_settings,
    )

    classification_outcome = None
    try:
        with observer.run(
            stage="classification",
            mailbox_id=email.mailbox_id,
            email_id=email_id,
            trace_id=trace_id,
        ) as classification_run_id:
            classifier_settings = load_classifier_settings(email.mailbox_id)
            structured_client = build_structured_client_from_settings(
                classifier_settings
            )
            outcome = StructuredClassifier(structured_client).classify(
                content,
                context.topics if context else [],
                context.active_fields if context else None,
            )
            classification_outcome = outcome
        if classification_run_id is not None:
            observer.record_usage(
                classification_run_id,
                input_tokens=outcome.prompt_tokens,
                output_tokens=outcome.completion_tokens,
                total_tokens=outcome.total_tokens,
            )
            observer.attach_metadata(
                classification_run_id,
                {
                    "structured_valid": outcome.structured_valid,
                    "fallback_parser_used": outcome.fallback_parser_used,
                    "repair_attempted": outcome.repair_attempted,
                    "attempts": outcome.attempts,
                    "topic_resolved": outcome.topic_resolved,
                    "latency_ms": outcome.latency_ms,
                },
            )
    except StructuredLLMError:
        store.mark_failed(email_id)
        raise
    except Exception:
        store.mark_failed(email_id)
        raise

    if classification_outcome is None or not classification_outcome.category:
        store.mark_failed(email_id)
        raise HTTPException(
            status_code=422,
            detail=(
                "Classification failed: the model did not return a valid "
                "structured result. Check your LLM configuration (max_tokens) "
                "and retry."
            ),
        )

    outcome = classification_outcome
    # Defense-in-depth: re-resolve the topic against the mailbox's topics
    # (the structured classifier already resolved; this also covers outcomes
    # from paths where resolution was skipped).
    from email_assistant.core.topics import resolve_topic

    topic_id, canonical = resolve_topic(
        context.topics if context else [], outcome.topic
    )
    classification = ClassificationOut(
        category=outcome.category,
        topic=canonical or outcome.topic,
        priority=outcome.priority,
        summary=outcome.summary,
        custom={str(k): v for k, v in outcome.custom_fields.items()},
        topic_id=topic_id if topic_id is not None else outcome.topic_id,
        topic_raw=outcome.topic,
    )

    case = store.save_case(email_id, classification, "")
    if case is None:
        store.mark_failed(email_id)
        raise HTTPException(status_code=404, detail="Email not found")

    # Persist knowledge provenance for the draft (which chunks grounded it).
    if knowledge_refs:
        try:
            store.set_draft_knowledge_refs(email_id, knowledge_refs)
        except Exception:  # noqa: BLE001 - provenance is best effort
            pass

    # 3. Drafting via the CrewAI drafter (grounded in retrieved knowledge and
    #    the validated classification).
    import json as _json

    try:
        with observer.run(
            stage="email_processing",
            mailbox_id=email.mailbox_id,
            email_id=email_id,
            trace_id=trace_id,
        ) as processing_run_id:
            draft_result = EmailAssistant().draft_only_crew().kickoff(
                inputs={
                    "email_content": content,
                    "classification": _json.dumps(
                        {
                            "category": outcome.category,
                            "topic": outcome.topic,
                            "priority": outcome.priority,
                            "summary": outcome.summary,
                            "custom_fields": outcome.custom_fields,
                        },
                        ensure_ascii=False,
                    ),
                    "knowledge_context": knowledge_context or "(no knowledge available)",
                }
            )
        _record_usage(observer, processing_run_id, draft_result)
        draft = str(getattr(draft_result, "raw", "") or "")
    except Exception:
        store.mark_failed(email_id)
        raise

    if not draft.strip():
        store.mark_failed(email_id)
        raise HTTPException(
            status_code=502,
            detail="Drafting failed: the model returned an empty reply.",
        )

    saved = store.save_draft(email_id, draft)
    if saved is None:
        store.mark_failed(email_id)
        raise HTTPException(status_code=404, detail="Email not found")

    # 4. Persist accepted field values (already business-validated by the
    #    structured classifier; keys may be field ids or field names —
    #    resolve names against the mailbox's definitions).
    if outcome.custom_fields:
        fields_by_name = {
            str(f.get("name", "")).lower(): int(f["id"])
            for f in (context.active_fields if context else [])
        }
        values: dict[int, str] = {}
        for key, value in outcome.custom_fields.items():
            if isinstance(key, int) or str(key).isdigit():
                field_id = int(key)
            else:
                field_id = fields_by_name.get(str(key).lower())
                if field_id is None:
                    continue
            values[field_id] = _json.dumps(value)
        if values:
            try:
                store.fill_ai_case_field_values(email_id, values)
            except Exception:  # noqa: BLE001 - field persistence must not block
                pass

    return ProcessResponse(case=saved)


def _record_usage(observer: Observer, run_id: int | None, result) -> None:
    """Record token/model usage from a CrewAI result if available (best effort)."""
    if run_id is None:
        return
    try:
        usage = getattr(result, "usage_metrics", None) or getattr(
            result, "token_usage", None
        )
        if not usage:
            return
        observer.record_usage(
            run_id,
            input_tokens=usage.get("prompt_tokens") or usage.get("input_tokens"),
            output_tokens=usage.get("completion_tokens")
            or usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
    except Exception:  # noqa: BLE001 - best effort
        pass


@router.post("/process-all", response_model=dict)
def process_all_emails(
    mailbox_id: int | None = Query(default=None),
) -> dict:
    """Queue-process all pending emails sequentially (one at a time).

    Synchronous so FastAPI runs it in a worker thread; each email's status
    transitions new -> processing -> processed (or back to new on failure).
    """
    pending = store.list_pending_ids(mailbox_id)
    processed = 0
    failed: list[str] = []

    for email_id in pending:
        try:
            process_email(email_id)
            processed += 1
        except Exception:  # noqa: BLE001 - keep the queue running on failures
            failed.append(email_id)

    return {"queued": len(pending), "processed": processed, "failed": failed}


def load_classifier_settings(mailbox_id: int | None):
    """Resolve LLM settings for classification, honouring per-mailbox overrides.

    Mirrors the CrewAI per-stage override behaviour: the mailbox's
    classifier config / temperature / max_tokens win over the active global
    AI config.
    """
    from email_assistant.core.stage_defaults import effective_stage_settings
    from email_assistant.service import load_llm_settings

    settings = load_llm_settings()
    overrides: dict = {}
    if mailbox_id is not None:
        from email_assistant.core.settings_store import SettingsStore

        mailbox = SettingsStore().get_mailbox(mailbox_id)
        if mailbox:
            if mailbox.get("classifier_config_id"):
                from email_assistant.service import LLMSettings

                config = SettingsStore().get_ai_config(
                    int(mailbox["classifier_config_id"]), mask_secrets=False
                )
                if config:
                    settings = LLMSettings.from_generic(config)
            stage = SettingsStore().get_stage_settings("classification")
            overrides = effective_stage_settings("classification", stage)

    updates: dict = {}
    if overrides.get("temperature") is not None:
        updates["temperature"] = float(overrides["temperature"])
    if overrides.get("max_tokens") is not None:
        updates["max_tokens"] = int(overrides["max_tokens"])
    return settings.model_copy(update=updates) if updates else settings
