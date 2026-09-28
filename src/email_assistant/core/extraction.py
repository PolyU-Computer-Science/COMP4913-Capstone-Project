"""AI structured extraction of topic + custom fields.

The extraction client is abstracted so tests can run offline with a fake, and
a real LLM client can be swapped in later. The *service* is the authority: it
resolves the topic and validates each field against the mailbox's definitions,
so AI output never flows directly into the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ExtractionResult:
    topic: str = ""
    fields: list[dict[str, Any]] = field(default_factory=list)


class ExtractionClient(Protocol):
    """Extracts topic and field values from an email in one structured call."""

    def extract(
        self,
        email_content: str,
        topics: list[dict[str, Any]],
        fields: list[dict[str, Any]],
    ) -> ExtractionResult: ...


class FakeExtractionClient:
    """Deterministic offline extraction client (for tests)."""

    def __init__(self, result: ExtractionResult | None = None) -> None:
        self._result = result or ExtractionResult()

    def extract(
        self,
        email_content: str,
        topics: list[dict[str, Any]],
        fields: list[dict[str, Any]],
    ) -> ExtractionResult:
        return self._result


class ClassificationExtractionClient:
    """Builds an extraction result from the classifier's existing output.

    Uses the classifier's ``topic`` and ``custom`` field dict (keyed by field
    name or field id) without an extra LLM call. This is the default wiring;
    a real LLM extraction client can replace it.
    """

    def __init__(self, topic: str, custom: dict[str, Any]) -> None:
        self._topic = topic
        self._custom = custom or {}

    def extract(
        self,
        email_content: str,
        topics: list[dict[str, Any]],
        fields: list[dict[str, Any]],
    ) -> ExtractionResult:
        fields_by_name = {
            str(f.get("name", "")).lower(): int(f["id"]) for f in fields
        }
        field_items: list[dict[str, Any]] = []
        for key, value in self._custom.items():
            if isinstance(key, int) or str(key).isdigit():
                field_id = int(key)
            else:
                field_id = fields_by_name.get(str(key).lower())
                if field_id is None:
                    continue
            field_items.append({"field_id": field_id, "value": value})
        return ExtractionResult(topic=self._topic, fields=field_items)


def format_fields_prompt(fields: list[dict[str, Any]]) -> str:
    """Render mailbox field definitions for the extraction prompt."""
    active = [f for f in fields if f.get("status", "active") == "active"]
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
        "Return field values by field_id. Do not invent field names. "
        "If there is insufficient evidence, omit the field."
    )
    return "\n".join(lines)
