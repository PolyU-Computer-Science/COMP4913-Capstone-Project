"""OpenAI-compatible embedding client tests — all HTTP mocked."""

from __future__ import annotations

import pytest

from email_assistant.core.embeddings import EmbeddingConfig, embeddings_compatible
from email_assistant.core.openai_embeddings import (
    EmbeddingAuthError,
    OpenAICompatibleEmbeddingClient,
    EmbeddingPaymentError,
    EmbeddingRateLimitError,
    EmbeddingResponseError,
    EmbeddingServerError,
)


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class _FakeTransport:
    def __init__(self):
        self.calls: list[dict] = []
        self.handler = None

    def post(self, url, json):
        self.calls.append({"url": url, "json": json})
        if self.handler is None:
            raise AssertionError("no handler configured")
        return self.handler(json)


def _embedding_response(inputs: list[str], dim: int = 8) -> dict:
    return {
        "data": [
            {
                "index": i,
                "embedding": [float((i + j) % dim) for j in range(dim)],
            }
            for i, _ in enumerate(inputs)
        ]
    }


def _client(transport, model="qwen/qwen3-embedding-8b") -> OpenAICompatibleEmbeddingClient:
    return OpenAICompatibleEmbeddingClient(
        api_key="test-key", model=model, transport=transport, provider="openrouter"
    )


def test_single_embed_discovers_dimension() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200, _embedding_response(payload["input"], dim=10)
    )
    client = _client(transport)
    vectors = client.embed_documents(["hello world"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 10
    # Dimension discovered, not hardcoded.
    assert client.dim == 10


def test_dimension_is_not_hardcoded() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200, _embedding_response(payload["input"], dim=4096)
    )
    client = _client(transport)
    client.embed_query("x")
    assert client.dim == 4096


def test_config_identity_uses_discovered_dim() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200, _embedding_response(payload["input"], dim=7)
    )
    client = _client(transport)
    client.embed_query("x")
    config = client.config
    assert config.provider == "openrouter"
    assert config.model == "qwen/qwen3-embedding-8b"
    assert config.dim == 7


def test_batch_embedding_splits_requests() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200, _embedding_response(payload["input"], dim=4)
    )
    client = OpenAICompatibleEmbeddingClient(
        api_key="k", model="m", transport=transport, batch_size=3
    )
    texts = [f"chunk {i}" for i in range(7)]
    vectors = client.embed_documents(texts)
    assert len(vectors) == 7
    # 3 batches: 3 + 3 + 1.
    assert len(transport.calls) == 3
    assert [len(c["json"]["input"]) for c in transport.calls] == [3, 3, 1]


def test_auth_error_401() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(401, text="unauthorized")
    with pytest.raises(EmbeddingAuthError):
        _client(transport).embed_query("x")


def test_payment_error_402() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(402, text="credits")
    with pytest.raises(EmbeddingPaymentError):
        _client(transport).embed_query("x")


def test_rate_limit_429() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(429, text="rate limit")
    with pytest.raises(EmbeddingRateLimitError):
        _client(transport).embed_query("x")


def test_server_error_5xx() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(503, text="provider down")
    with pytest.raises(EmbeddingServerError):
        _client(transport).embed_query("x")


def test_wrong_vector_count_rejected() -> None:
    transport = _FakeTransport()
    # Request 2 inputs, server returns 1 vector.
    transport.handler = lambda payload: _FakeResponse(
        200, _embedding_response(["only-one"], dim=8)
    )
    with pytest.raises(EmbeddingResponseError):
        _client(transport).embed_documents(["a", "b"])


def test_empty_embedding_rejected() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(200, {"data": []})
    with pytest.raises(EmbeddingResponseError):
        _client(transport).embed_query("x")


def test_missing_embedding_field_rejected() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200, {"data": [{"index": 0}]}
    )
    with pytest.raises(EmbeddingResponseError):
        _client(transport).embed_query("x")


def test_inconsistent_batch_dimensions_rejected() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200,
        {
            "data": [
                {"index": 0, "embedding": [1.0, 2.0]},
                {"index": 1, "embedding": [1.0, 2.0, 3.0]},
            ]
        },
    )
    with pytest.raises(EmbeddingResponseError):
        _client(transport).embed_documents(["a", "b"])


def test_invalid_json_rejected() -> None:
    transport = _FakeTransport()

    class _BadResponse:
        status_code = 200
        text = "not json"

        def json(self):
            raise ValueError("bad json")

    transport.handler = lambda payload: _BadResponse()
    with pytest.raises(EmbeddingResponseError):
        _client(transport).embed_query("x")


def test_openrouter_config_incompatible_with_hashing() -> None:
    openrouter_config = EmbeddingConfig("openrouter", "qwen/qwen3-embedding-8b", 4096)
    hashing_config = EmbeddingConfig("hashing", "hashing", 256)
    assert embeddings_compatible(openrouter_config, hashing_config) is False
    assert embeddings_compatible(openrouter_config, openrouter_config) is True
