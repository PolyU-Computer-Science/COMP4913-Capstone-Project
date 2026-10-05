"""Pytest configuration: ensure the settings DB is hermetic per test."""

import pytest


@pytest.fixture(autouse=True)
def _hermetic_settings_db(tmp_path, monkeypatch):
    """Point the stores at temp DBs so tests never touch data/."""
    monkeypatch.setenv("SQLITE_EMAIL_DB", str(tmp_path / "emails.db"))
    monkeypatch.setenv("SQLITE_SETTINGS_DB", str(tmp_path / "settings.db"))
    monkeypatch.delenv("SETTINGS_ENCRYPTION_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_real_llm_calls(monkeypatch):
    """Hard-offline guard: un-mocked LLM calls with no fake transport fail.

    Tests that exercise the client itself inject a fake HTTP transport
    (``OpenAICompatibleStructuredClient(transport=...)``) and are untouched.
    Any pipeline test that forgot to mock classification gets a loud error
    instead of a real (paid) network call.
    """
    import email_assistant.core.structured_llm as structured_llm_module
    from email_assistant.core.structured_llm import OpenAICompatibleStructuredClient

    original_generate = OpenAICompatibleStructuredClient.generate

    def _guarded_generate(self, *, system, user, response_model):  # noqa: ANN001
        if getattr(self, "_transport", None) is None:
            raise AssertionError(
                "Test attempted a real LLM call. Mock "
                "StructuredClassifier.classify (or inject a fake transport) "
                "in this test."
            )
        return original_generate(self, system=system, user=user, response_model=response_model)

    monkeypatch.setattr(
        OpenAICompatibleStructuredClient, "generate", _guarded_generate
    )
    # Also stub the factory so building a client never needs provider config.
    monkeypatch.setattr(
        structured_llm_module,
        "build_structured_client_from_settings",
        lambda settings: object(),
    )
