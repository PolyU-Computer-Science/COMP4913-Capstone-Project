"""Settings endpoints for AI configs, per-stage settings, and mail accounts."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from email_assistant.core.settings_store import SettingsStore
from email_assistant.service import (
    LLMConfigurationError,
    LLMSettings,
    create_llm,
)

from backend.app.schemas import (
    AIConfig,
    AIConfigIn,
    MailAccount,
    MailAccountIn,
    StageConfig,
    StagesSettings,
    TestResult,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _store() -> SettingsStore:
    """Create a store; the DB path is resolved from env at call time."""
    return SettingsStore()


def _resolve(data: dict, existing: dict | None = None) -> LLMSettings:
    api_key = str(data.get("api_key") or "") or str(
        (existing or {}).get("api_key") or ""
    )
    return LLMSettings.from_generic({**data, "api_key": api_key or None})


def _run_test(settings: LLMSettings) -> TestResult:
    try:
        llm = create_llm(settings)
        response = llm.call("Reply with the single word: OK")
        return TestResult(ok=True, message=f"Connected: {str(response)[:120]}")
    except Exception as error:  # noqa: BLE001 - report any failure to the UI
        return TestResult(ok=False, message=str(error))


def _validate_error(error: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


# ---- AI configs ----

@router.get("/ai", response_model=list[AIConfig])
def list_ai_configs() -> list[AIConfig]:
    return [AIConfig(**config) for config in _store().list_ai_configs()]


@router.post("/ai", response_model=AIConfig, status_code=201)
def create_ai_config(payload: AIConfigIn) -> AIConfig:
    try:
        _resolve(payload.model_dump())
    except (LLMConfigurationError, ValidationError) as error:
        raise _validate_error(error) from error

    config = _store().create_ai_config(payload.model_dump())
    return AIConfig(**config)


@router.put("/ai/{config_id}", response_model=AIConfig)
def update_ai_config(config_id: int, payload: AIConfigIn) -> AIConfig:
    store = _store()
    existing = store.get_ai_config(config_id, mask_secrets=False)
    if existing is None:
        raise HTTPException(status_code=404, detail="AI config not found")

    try:
        _resolve(payload.model_dump(), existing)
    except (LLMConfigurationError, ValidationError) as error:
        raise _validate_error(error) from error

    config = store.update_ai_config(config_id, payload.model_dump())
    assert config is not None
    return AIConfig(**config)


@router.delete("/ai/{config_id}")
def delete_ai_config(config_id: int) -> dict:
    if not _store().delete_ai_config(config_id):
        raise HTTPException(status_code=404, detail="AI config not found")
    return {"ok": True}


@router.post("/ai/{config_id}/activate", response_model=AIConfig)
def activate_ai_config(config_id: int) -> AIConfig:
    config = _store().set_active_ai_config(config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="AI config not found")
    return AIConfig(**config)


@router.post("/ai/test", response_model=TestResult)
def test_ai_config(payload: AIConfigIn) -> TestResult:
    try:
        settings = _resolve(payload.model_dump())
    except (LLMConfigurationError, ValidationError) as error:
        return TestResult(ok=False, message=str(error))
    return _run_test(settings)


@router.post("/ai/{config_id}/test", response_model=TestResult)
def test_saved_ai_config(config_id: int) -> TestResult:
    config = _store().get_ai_config(config_id, mask_secrets=False)
    if config is None:
        return TestResult(ok=False, message="AI config not found")
    try:
        settings = LLMSettings.from_generic(config)
    except (LLMConfigurationError, ValidationError) as error:
        return TestResult(ok=False, message=str(error))
    return _run_test(settings)


# ---- stage settings ----

@router.get("/stages", response_model=StagesSettings)
def get_stage_settings() -> StagesSettings:
    from email_assistant.core.stage_defaults import effective_stage_settings

    store = _store()
    return StagesSettings(
        classification=StageConfig(
            **effective_stage_settings(
                "classification", store.get_stage_settings("classification")
            )
        ),
        draft=StageConfig(
            **effective_stage_settings("draft", store.get_stage_settings("draft"))
        ),
    )


@router.get("/stages/migration-warnings", response_model=list[str])
def get_stage_migration_warnings() -> list[str]:
    """Return seed-migration warnings (e.g. a custom prompt predating the
    classification-context update). Runs the migration check once per
    response; warnings persist until the prompt is updated."""
    return _store().migrate_stage_seeds()


@router.put("/stages", response_model=StagesSettings)
def put_stage_settings(payload: StagesSettings) -> StagesSettings:
    store = _store()
    store.set_stage_settings(
        "classification", payload.classification.model_dump()
    )
    store.set_stage_settings("draft", payload.draft.model_dump())
    return get_stage_settings()


# ---- mail accounts ----

@router.get("/mail", response_model=list[MailAccount])
def list_mail_accounts() -> list[MailAccount]:
    return [MailAccount(**account) for account in _store().list_mail_accounts()]


@router.post("/mail", response_model=MailAccount, status_code=201)
def create_mail_account(payload: MailAccountIn) -> MailAccount:
    account = _store().create_mail_account(payload.model_dump())
    return MailAccount(**account)


@router.put("/mail/{account_id}", response_model=MailAccount)
def update_mail_account(account_id: int, payload: MailAccountIn) -> MailAccount:
    account = _store().update_mail_account(account_id, payload.model_dump())
    if account is None:
        raise HTTPException(status_code=404, detail="Mail account not found")
    return MailAccount(**account)


@router.delete("/mail/{account_id}")
def delete_mail_account(account_id: int) -> dict:
    if not _store().delete_mail_account(account_id):
        raise HTTPException(status_code=404, detail="Mail account not found")
    return {"ok": True}
