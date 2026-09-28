from __future__ import annotations

from email_assistant.core.stage_defaults import effective_stage_settings


def test_defaults_are_builtin() -> None:
    settings = effective_stage_settings("classification", {})

    assert settings["role"] == "Email Classifier"
    assert settings["goal"]
    assert settings["backstory"]
    assert "{email_content}" in settings["prompt"]
    assert settings["max_tokens"] is None
    assert settings["temperature"] is None


def test_overrides_win_over_builtin() -> None:
    settings = effective_stage_settings(
        "classification",
        {
            "role": "Custom Role",
            "prompt": "Custom prompt",
            "max_tokens": 111,
            "temperature": 0.1,
        },
    )

    assert settings["role"] == "Custom Role"
    assert settings["prompt"] == "Custom prompt"
    assert settings["max_tokens"] == 111
    assert settings["temperature"] == 0.1


def test_empty_override_falls_back_to_builtin() -> None:
    settings = effective_stage_settings(
        "classification", {"role": "", "goal": "", "prompt": ""}
    )

    assert settings["role"] == "Email Classifier"
    assert settings["goal"]
    assert "{email_content}" in settings["prompt"]


def test_draft_defaults() -> None:
    settings = effective_stage_settings("draft", {})

    assert settings["role"] == "Reply Drafter"
    assert settings["prompt"]
    assert "{knowledge_context}" in settings["prompt"]
