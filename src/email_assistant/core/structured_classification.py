"""Structured classification pipeline (5-layer contract).

Ties the structured LLM client to the existing business validators:

    raw response → JSON extraction → tolerant repair → Pydantic validation
                  → business validation (topic resolution + field validation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from email_assistant.core.structured_llm import OpenAICompatibleStructuredClient, StructuredLLMResult


class ClassificationContract(BaseModel):
    """The unified structured output contract for classification."""

    category: str = Field(description="question, incident, problem, task, or spam")
    topic: str = Field(default="", description="topic name from the mailbox's available topics")
    priority: str = Field(default="normal", description="low, normal, high, or urgent")
    summary: str = Field(default="")
    custom_fields: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ClassificationOutcome:
    """A classification result after business validation."""

    category: str = ""
    topic: str = ""
    topic_id: int | None = None
    topic_resolved: bool = False
    priority: str = "normal"
    summary: str = ""
    custom_fields: dict[str, Any] = field(default_factory=dict)
    structured_valid: bool = False
    fallback_parser_used: bool = False
    repair_attempted: bool = False
    attempts: int = 0
    returned_model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float = 0.0
    error: str | None = None


def _format_fields_prompt(fields: list[dict[str, Any]] | None) -> str:
    """Render mailbox field definitions so the model knows each field id."""
    active = [
        f for f in (fields or []) if f.get("status", "active") == "active"
    ]
    if not active:
        return ""
    lines = ["Available fields:"]
    for f in active:
        type_info = str(f.get("type", "text"))
        options = f.get("options") or ""
        if type_info in ("select", "multiselect") and options:
            type_info = f"{type_info} [{options}]"
        lines.append(
            f"- ID: {f['id']}, name: {f.get('name', '')}, type: {type_info}"
        )
        prompt = (f.get("prompt") or "").strip()
        if prompt:
            lines.append(f"  Extraction guidance: {prompt}")
    lines.append(
        'Return field values in "custom_fields" keyed by field ID. '
        "If there is insufficient evidence, omit the field."
    )
    return "\n".join(lines)


def build_classification_prompt(
    *,
    email_content: str,
    topics: list[dict[str, Any]],
    fields: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Return (system, user) prompts for structured classification."""
    system = (
        "You are an email classification agent. Respond with ONLY a single "
        "valid JSON object matching this schema: "
        '{"category": str, "topic": str, "priority": str, '
        '"summary": str, "custom_fields": object}. '
        "The topic must be one of the provided available topics if one fits, "
        "otherwise empty. Do not invent topics."
    )
    topic_lines = "\n".join(
        f"- {t.get('name', '')}" for t in topics if t.get("status", "active") == "active"
    )
    fields_block = _format_fields_prompt(fields)
    user = (
        f"Available topics:\n{topic_lines or '(none)'}\n\n"
        + (f"{fields_block}\n\n" if fields_block else "")
        + f"Email:\n{email_content}\n\n"
        "Return ONLY the JSON object."
    )
    return system, user


class StructuredClassifier:
    """Runs classification through the structured client + business validators."""

    def __init__(self, client: OpenAICompatibleStructuredClient) -> None:
        self._client = client

    def classify(
        self,
        email_content: str,
        topics: list[dict[str, Any]],
        fields: list[dict[str, Any]] | None = None,
    ) -> ClassificationOutcome:
        from email_assistant.core.field_validation import validate_field_value
        from email_assistant.core.topics import resolve_topic

        system, user = build_classification_prompt(
            email_content=email_content, topics=topics, fields=fields
        )
        result: StructuredLLMResult[ClassificationContract] = self._client.generate(
            system=system, user=user, response_model=ClassificationContract
        )

        outcome = ClassificationOutcome(
            structured_valid=result.valid,
            fallback_parser_used=result.fallback_parser_used,
            repair_attempted=result.repair_attempted,
            attempts=result.attempts,
            returned_model=result.returned_model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            latency_ms=result.latency_ms,
            error=result.error,
        )

        if result.data is None:
            return outcome

        data = result.data
        outcome.category = data.category
        outcome.priority = data.priority
        outcome.summary = data.summary

        # Business validation: topic must resolve against mailbox topics.
        topic_id, canonical = resolve_topic(topics, data.topic)
        outcome.topic_id = topic_id
        outcome.topic_resolved = topic_id is not None
        outcome.topic = canonical if canonical else data.topic

        # Business validation: custom fields must pass field validation.
        valid_fields: dict[str, Any] = {}
        if fields:
            fields_by_id = {int(f["id"]): f for f in fields}
            for key, value in (data.custom_fields or {}).items():
                try:
                    field_id = int(key)
                except (TypeError, ValueError):
                    continue
                definition = fields_by_id.get(field_id)
                if definition is None:
                    continue
                ok, _ = validate_field_value(definition, value)
                if ok:
                    valid_fields[key] = value
        outcome.custom_fields = valid_fields

        return outcome
