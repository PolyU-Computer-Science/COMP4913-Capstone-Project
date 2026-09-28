"""Stage settings defaults + DB override merging.

Defaults come from ``stage_seeds`` (built-in constants). The DB is the
single source of truth at runtime: it is seeded once on startup and then
read directly.
"""

from __future__ import annotations

from typing import Any

from email_assistant.core.stage_seeds import STAGE_SEEDS


def effective_stage_settings(stage: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge built-in defaults with DB values (non-empty DB values win)."""
    merged = dict(STAGE_SEEDS[stage])
    for field in ("role", "goal", "backstory", "prompt"):
        value = overrides.get(field)
        if value:
            merged[field] = value
    merged["max_tokens"] = overrides.get("max_tokens")
    merged["temperature"] = overrides.get("temperature")
    return merged
