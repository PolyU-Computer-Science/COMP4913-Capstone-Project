"""OpenAI-compatible embeddings client.

Implements the ``EmbeddingClient`` protocol against any OpenAI-compatible
``/embeddings`` endpoint: OpenRouter, Ollama, OpenAI, LM Studio, vLLM, etc.
The endpoint only differs by base URL and whether an API key is required.
The embedding dimension is discovered from the first response — never
hardcoded — so a model swap is detected by the existing
``EmbeddingConfig(provider, model, dim)`` compatibility layer.

All network access goes through a pluggable transport (``httpx`` by default)
so tests can mock HTTP and never incur a paid call.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from email_assistant.core.embeddings import EmbeddingClient

load_dotenv(override=False)

DEFAULT_BATCH_SIZE = 32

# Per-provider endpoint defaults (all OpenAI-compatible /embeddings).
PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
    "mistral": "https://api.mistral.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "local": "",
}

# Official API key env var per provider (empty = no key needed).
PROVIDER_API_KEY_ENVS: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "local": "LOCAL_API_KEY",
}

# Providers that cannot work without an API key.
PROVIDERS_REQUIRING_API_KEY = set(PROVIDER_API_KEY_ENVS) - {"ollama", "local"}

# Per-provider default embedding models.
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openrouter": "qwen/qwen3-embedding-8b",
    "openai": "text-embedding-3-small",
    "ollama": "qwen3-embedding-4b",
    "mistral": "mistral-embed",
    "gemini": "text-embedding-004",
    "local": "",
}

# Constructor fallbacks (overridden per provider by the factory).
DEFAULT_BASE_URL = PROVIDER_BASE_URLS["openrouter"]
DEFAULT_MODEL = PROVIDER_DEFAULT_MODELS["openrouter"]


class OpenAICompatibleEmbeddingError(RuntimeError):
    """Base class for embedding endpoint errors."""


class EmbeddingAuthError(OpenAICompatibleEmbeddingError):
    """401 — missing/invalid API key."""


class EmbeddingPaymentError(OpenAICompatibleEmbeddingError):
    """402 — insufficient credits / payment required."""


class EmbeddingRateLimitError(OpenAICompatibleEmbeddingError):
    """429 — rate limited."""


class EmbeddingServerError(OpenAICompatibleEmbeddingError):
    """5xx — upstream provider / server error."""


class EmbeddingResponseError(OpenAICompatibleEmbeddingError):
    """Malformed / missing / dimension-inconsistent response."""


class OpenAICompatibleEmbeddingClient(EmbeddingClient):
    """Semantic embeddings via an OpenAI-compatible /embeddings endpoint."""

    provider: str = "openai-compatible"

    def __init__(
        self,
        api_key: str = "",
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        batch_size: int = DEFAULT_BATCH_SIZE,
        transport: Any = None,
        provider: str = "openai-compatible",
    ) -> None:
        self.model = model
        self.provider = provider
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._batch_size = max(1, int(batch_size))
        self._dim = 0
        self._transport = transport

    @property
    def dim(self) -> int:
        """Discovered embedding dimension (0 until first successful call)."""
        return self._dim

    def _client(self):
        if self._transport is not None:
            return self._transport
        import httpx

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        )

    def _post(self, payload: dict) -> dict:
        import httpx

        client = self._client()
        try:
            response = client.post("/embeddings", json=payload)
        except httpx.TimeoutException as error:
            raise OpenAICompatibleEmbeddingError(
                f"Embedding request timed out: {error}"
            ) from error
        except httpx.RequestError as error:
            raise OpenAICompatibleEmbeddingError(
                f"Embedding request failed: {error}"
            ) from error

        status = response.status_code
        if status == 401:
            raise EmbeddingAuthError(f"Embedding authentication failed (401)")
        if status == 402:
            raise EmbeddingPaymentError(f"Insufficient credits (402)")
        if status == 429:
            raise EmbeddingRateLimitError(f"Rate limit exceeded (429)")
        if status >= 500:
            raise EmbeddingServerError(f"Embedding server error ({status})")
        if status >= 400:
            raise OpenAICompatibleEmbeddingError(
                f"Embedding error ({status}): {_snippet(response.text)}"
            )

        try:
            return response.json()
        except ValueError as error:
            raise EmbeddingResponseError(
                "Invalid JSON response from embedding endpoint"
            ) from error

    def _extract_vectors(self, body: dict, expected: int) -> list[list[float]]:
        data = body.get("data") or []
        if not data:
            raise EmbeddingResponseError("Empty embedding response")
        if len(data) != expected:
            raise EmbeddingResponseError(
                f"Expected {expected} embeddings, got {len(data)}"
            )

        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding")
            if not embedding:
                raise EmbeddingResponseError("Missing embedding vector in response")
            vectors.append([float(x) for x in embedding])

        dims = {len(v) for v in vectors}
        if len(dims) != 1:
            raise EmbeddingResponseError("Inconsistent embedding dimensions in batch")
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            body = self._post({"model": self.model, "input": batch})
            vectors = self._extract_vectors(body, len(batch))
            all_vectors.extend(vectors)

        if all_vectors:
            self._dim = len(all_vectors[0])
        return all_vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            raise EmbeddingResponseError("Empty embedding response for query")
        return vectors[0]


def _snippet(text: str) -> str:
    return (text or "")[:200]


def build_openai_compatible_embedding_client(
    provider: str = "openrouter",
) -> OpenAICompatibleEmbeddingClient:
    """Build a client for the given provider from environment variables.

    Shared env vars: ``EMBEDDING_MODEL``, ``EMBEDDING_BASE_URL``,
    ``EMBEDDING_BATCH_SIZE``. API keys use the provider's official env var
    (``OPENROUTER_API_KEY``, ``OPENAI_API_KEY``, ``MISTRAL_API_KEY``,
    ``GEMINI_API_KEY``); Ollama and local servers need no key.
    """
    provider = (provider or "").strip().lower()
    if provider not in PROVIDER_BASE_URLS:
        from email_assistant.core.embeddings import EmbeddingConfigurationError

        raise EmbeddingConfigurationError(f"Unknown embedding provider: {provider!r}")

    api_key = ""
    key_env = PROVIDER_API_KEY_ENVS.get(provider)
    if key_env:
        api_key = os.environ.get(key_env, "").strip()

    if provider in PROVIDERS_REQUIRING_API_KEY and not api_key:
        from email_assistant.core.embeddings import EmbeddingConfigurationError

        raise EmbeddingConfigurationError(
            f"EMBEDDING_PROVIDER={provider} but {key_env} is not set"
        )

    default_base_url = PROVIDER_BASE_URLS[provider]
    base_url = (
        os.environ.get("EMBEDDING_BASE_URL", "").strip()
        or os.environ.get("OPENROUTER_BASE_URL", "").strip()
        or default_base_url
    )
    model = (
        os.environ.get("EMBEDDING_MODEL", "").strip()
        or PROVIDER_DEFAULT_MODELS[provider]
    )
    batch_size = int(os.environ.get("EMBEDDING_BATCH_SIZE", DEFAULT_BATCH_SIZE))

    return OpenAICompatibleEmbeddingClient(
        api_key=api_key,
        model=model,
        base_url=base_url,
        batch_size=batch_size,
        provider=provider,
    )
