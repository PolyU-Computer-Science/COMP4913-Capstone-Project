"""FastAPI application for the email assistant."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routers import (
    cases,
    connectors,
    emails,
    knowledge,
    mailboxes,
    observability,
    settings,
    stats,
)

load_dotenv(override=False)

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    """Build the FastAPI application with CORS and routers."""
    app = FastAPI(
        title="Email Assistant API",
        description="Backend API for the agentic AI email assistant.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(emails.router)
    app.include_router(cases.router)
    app.include_router(stats.router)
    app.include_router(settings.router)
    app.include_router(knowledge.router)
    app.include_router(mailboxes.router)
    app.include_router(connectors.router)
    app.include_router(observability.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()


def run() -> None:
    """Run the API server with uvicorn."""
    import uvicorn

    from email_assistant.core.settings_store import SettingsStore

    store = SettingsStore()
    store.ensure_default_ai_config()
    store.ensure_default_stage_settings()
    store.ensure_default_mailbox()

    # Backfill any legacy emails that predate mailbox scoping.
    try:
        from email_assistant.core.migrations import migrate_legacy_emails

        migrated = migrate_legacy_emails()
        if migrated:
            print(f"Migrated {migrated} legacy email(s) to the Legacy mailbox.")
    except Exception:  # noqa: BLE001 - migration must never block startup
        print("WARNING: legacy email migration failed; skipping.")

    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=True)
