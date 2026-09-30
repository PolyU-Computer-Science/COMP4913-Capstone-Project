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
    from email_assistant.core.topics import (
        format_topics_prompt,
        resolve_topic,
    )

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
    available_topics = (
        format_topics_prompt(context.topics) if context else ""
    )

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

    # 2. Classifier + Drafter (single CrewAI sequential crew).
    try:
        with observer.run(
            stage="email_processing",
            mailbox_id=email.mailbox_id,
            email_id=email_id,
            trace_id=trace_id,
        ) as processing_run_id:
            result = EmailAssistant().crew().kickoff(
                inputs={
                    "email_content": content,
                    "available_topics": available_topics,
                    "knowledge_context": knowledge_context or "(no knowledge available)",
                }
            )
        _record_usage(observer, processing_run_id, result)
    except Exception:
        store.mark_failed(email_id)
        raise

    classification = None
    if result.pydantic is not None:
        classification = ClassificationOut(**result.pydantic.model_dump())
    else:
        from email_assistant.core.classification_parser import (
            parse_classification,
        )

        tasks_output = getattr(result, "tasks_output", None) or []
        if tasks_output:
            parsed = parse_classification(tasks_output[0].raw or "")
            if parsed is not None:
                classification = ClassificationOut(**parsed.model_dump())

    if classification is None:
        store.mark_failed(email_id)
        raise HTTPException(
            status_code=422,
            detail=(
                "Classification failed: the model did not return a valid "
                "structured result. Check your LLM configuration (max_tokens) "
                "and retry."
            ),
        )

    # Resolve the free-form topic against the mailbox's configured topics.
    topic_id, canonical = resolve_topic(
        context.topics if context else [], classification.topic
    )
    classification.topic_id = topic_id
    classification.topic_raw = classification.topic
    if canonical:
        classification.topic = canonical

    case = store.save_case(email_id, classification, result.raw)
    if case is None:
        store.mark_failed(email_id)
        raise HTTPException(status_code=404, detail="Email not found")

    # Persist knowledge provenance for the draft (which chunks grounded it).
    if knowledge_refs:
        try:
            store.set_draft_knowledge_refs(email_id, knowledge_refs)
        except Exception:  # noqa: BLE001 - provenance is best effort
            pass

    # 3. AI field extraction (structured, mailbox-scoped, partial success).
    if context and context.active_fields:
        from email_assistant.core.extraction import ClassificationExtractionClient
        from email_assistant.core.extraction_service import (
            ExtractionService,
            outcome_to_values_json,
        )

        client = ClassificationExtractionClient(
            classification.topic, classification.custom
        )
        extraction_service = ExtractionService(client)
        try:
            with observer.run(
                stage="field_extraction",
                mailbox_id=email.mailbox_id,
                email_id=email_id,
                trace_id=trace_id,
            ) as extraction_run_id:
                outcome = extraction_service.extract(
                    content, context.topics, context.active_fields
                )
            observer.attach_metadata(
                extraction_run_id,
                {
                    "topic_resolved": outcome.topic_resolved,
                    "fields_proposed": outcome.fields_proposed,
                    "fields_accepted": outcome.fields_accepted,
                    "fields_rejected": outcome.fields_rejected,
                },
            )
            values = outcome_to_values_json(outcome)
            if values:
                store.fill_ai_case_field_values(email_id, values)
        except Exception:  # noqa: BLE001 - extraction failure must not block
            pass

    return ProcessResponse(case=case)


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
