"""Observability wrapper.

Best-effort timing/tracing around pipeline stages. Observer write failures are
logged and swallowed so they never break email processing.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from email_assistant.core.observability_store import ObservabilityStore

logger = logging.getLogger(__name__)


class Observer:
    """Records processing runs with latency and token usage."""

    def __init__(self, store: ObservabilityStore | None = None) -> None:
        self._store = store or ObservabilityStore()

    @contextmanager
    def run(
        self,
        *,
        stage: str,
        mailbox_id: int | None = None,
        email_id: str | None = None,
        case_id: str | None = None,
        trace_id: str | None = None,
        parent_run_id: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        **metadata: Any,
    ) -> Iterator[int]:
        """Context manager that times a stage and records its result.

        Yields the run id so the caller can attach token usage on success.
        """
        # Auto-generate a trace id so every run is attributable to a pipeline.
        if trace_id is None:
            import uuid

            trace_id = uuid.uuid4().hex
        try:
            run_id = self._store.start_run(
                {
                    "trace_id": trace_id,
                    "parent_run_id": parent_run_id,
                    "mailbox_id": mailbox_id,
                    "email_id": email_id,
                    "case_id": case_id,
                    "stage": stage,
                    "provider": provider,
                    "model": model,
                }
            )
        except Exception:  # noqa: BLE001 - observability is best effort
            logger.warning("Observer start failed", exc_info=True)
            run_id = None

        start = time.perf_counter()
        status = "success"
        error_type = None
        error_message = None

        try:
            yield run_id  # type: ignore[misc]
        except Exception as error:  # noqa: BLE001
            status = "failed"
            error_type = type(error).__name__
            error_message = str(error)
            raise
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            if run_id is not None:
                try:
                    self._store.finish_run(
                        run_id,
                        status=status,
                        latency_ms=round(elapsed, 2),
                        metadata=metadata,
                        error_type=error_type,
                        error_message=error_message,
                    )
                except Exception:  # noqa: BLE001
                    logger.warning("Observer finish failed", exc_info=True)

    def record_usage(self, run_id: int | None, **tokens: Any) -> None:
        """Attach token usage to a finished run (best effort)."""
        if run_id is None:
            return
        try:
            self._store.record_usage(run_id, **tokens)
        except Exception:  # noqa: BLE001
            logger.warning("Observer record_usage failed", exc_info=True)

    def attach_metadata(self, run_id: int | None, metadata: dict[str, Any]) -> None:
        """Replace a finished run's metadata (best effort)."""
        if run_id is None:
            return
        try:
            self._store.attach_metadata(run_id, metadata)
        except Exception:  # noqa: BLE001
            logger.warning("Observer attach_metadata failed", exc_info=True)
