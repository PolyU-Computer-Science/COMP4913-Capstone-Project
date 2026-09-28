"""MiMo tool planner (6C.4).

The planner proposes a controlled tool action from an email using structured
LLM output. The proposal is *not* authoritative — it is validated against the
mailbox's allowed tools and each tool's input schema before any execution.

MiMo currently must not be assumed to support native function calling, so the
planner produces a JSON ``ActionProposal`` which the backend validates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from email_assistant.core.structured_llm import OpenAICompatibleStructuredClient


class ActionProposal(BaseModel):
    needs_tool: bool = False
    connector_id: int | None = None
    tool_name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


@dataclass
class ToolPlanResult:
    proposal: ActionProposal | None = None
    valid: bool = False
    error: str | None = None
    returned_model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float = 0.0


def build_tool_planner_prompt(
    *,
    email_content: str,
    allowed_tools: list[dict[str, Any]],
) -> tuple[str, str]:
    """Build (system, user) prompts for tool planning."""
    system = (
        "You are a tool-planning agent for an email assistant. Decide whether "
        "the email requires an external tool call, and if so propose exactly "
        "one tool from the allowed tools. Respond with ONLY a single valid "
        'JSON object: {"needs_tool": bool, "connector_id": int|null, '
        '"tool_name": str, "arguments": object, "reason": str}. '
        "Do not propose tools outside the allowed list. Extract only the "
        "minimum arguments needed by the tool."
    )

    tool_lines = []
    for tool in allowed_tools:
        tool_lines.append(
            f"- connector_id={tool['connector_id']}, tool={tool['name']}: "
            f"{tool.get('description', '')}"
        )
    tools_text = "\n".join(tool_lines) or "(no tools allowed)"

    user = (
        f"Allowed tools:\n{tools_text}\n\n"
        f"Email:\n{email_content}\n\n"
        "Return ONLY the JSON object."
    )
    return system, user


class ToolPlanner:
    """Produces a validated ActionProposal via structured LLM output."""

    def __init__(self, client: OpenAICompatibleStructuredClient) -> None:
        self._client = client

    def plan(
        self,
        email_content: str,
        allowed_tools: list[dict[str, Any]],
    ) -> ToolPlanResult:
        system, user = build_tool_planner_prompt(
            email_content=email_content, allowed_tools=allowed_tools
        )
        result = self._client.generate(
            system=system, user=user, response_model=ActionProposal
        )

        plan = ToolPlanResult(
            valid=result.valid,
            error=result.error,
            returned_model=result.returned_model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            latency_ms=result.latency_ms,
        )
        if result.data is not None:
            plan.proposal = result.data
        return plan
