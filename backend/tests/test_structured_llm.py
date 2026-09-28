"""Phase 5 — MiMo structured runtime contract tests (mocked HTTP)."""

from __future__ import annotations

import pytest

from email_assistant.core.structured_classification import (
    ClassificationContract,
    StructuredClassifier,
)
from email_assistant.core.structured_llm import (
    OpenAICompatibleStructuredClient,
    StructuredLLMAuthError,
    StructuredLLMPaymentError,
    StructuredLLMRateLimitError,
    StructuredLLMServerError,
    StructuredLLMResponseError,
    extract_json_object,
)


class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


def _chat_response(content: str, model="xiaomi/mimo-v2.5-pro", usage=None) -> dict:
    return {
        "model": model,
        "choices": [{"message": {"content": content}}],
        "usage": usage
        or {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


class _FakeTransport:
    def __init__(self):
        self.calls = 0
        self.handler = None

    def post(self, url, json):
        self.calls += 1
        if self.handler is None:
            raise AssertionError("no handler")
        return self.handler(json)


def _client(transport, max_retries=1) -> OpenAICompatibleStructuredClient:
    return OpenAICompatibleStructuredClient(
        api_key="k",
        model="xiaomi/mimo-v2.5-pro",
        transport=transport,
        max_retries=max_retries,
        provider="openrouter",
    )


def test_extract_json_from_plain_fenced_and_wrapped() -> None:
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('text {"a": 2} tail') == {"a": 2}
    assert extract_json_object('```json\n{"a": 3}\n```') == {"a": 3}
    assert extract_json_object("no json") is None


def test_valid_json_returns_pydantic_model() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200,
        _chat_response(
            '{"category": "question", "topic": "refund", "priority": "normal", '
            '"urgency_score": 3, "summary": "s", "custom_fields": {}}'
        ),
    )
    result = _client(transport).generate(
        system="s", user="u", response_model=ClassificationContract
    )
    assert result.valid is True
    assert result.data.category == "question"
    assert result.returned_model == "xiaomi/mimo-v2.5-pro"
    assert result.total_tokens == 150
    assert result.attempts == 1


def test_observability_records_usage_and_latency() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200,
        _chat_response(
            '{"category": "spam", "topic": "", "priority": "low", '
            '"urgency_score": 0, "summary": "", "custom_fields": {}}'
        ),
    )
    result = _client(transport).generate(
        system="s", user="u", response_model=ClassificationContract
    )
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 50
    assert result.latency_ms >= 0


def test_auth_401_raises_immediately_no_retry() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(401, text="unauthorized")
    with pytest.raises(StructuredLLMAuthError):
        _client(transport, max_retries=3).generate(
            system="s", user="u", response_model=ClassificationContract
        )
    assert transport.calls == 1


def test_payment_402_raises_immediately() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(402, text="credits")
    with pytest.raises(StructuredLLMPaymentError):
        _client(transport, max_retries=3).generate(
            system="s", user="u", response_model=ClassificationContract
        )
    assert transport.calls == 1


def test_rate_limit_429_retries() -> None:
    transport = _FakeTransport()
    responses = [
        _FakeResponse(429, text="rate limit"),
        _FakeResponse(
            200,
            _chat_response('{"category": "task", "topic": "", "priority": "normal", "urgency_score": 1, "summary": "", "custom_fields": {}}'),
        ),
    ]
    transport.handler = lambda payload: responses.pop(0)
    result = _client(transport, max_retries=2).generate(
        system="s", user="u", response_model=ClassificationContract
    )
    assert result.valid is True
    assert result.attempts == 2


def test_server_error_5xx_retries() -> None:
    transport = _FakeTransport()
    responses = [
        _FakeResponse(503, text="down"),
        _FakeResponse(
            200,
            _chat_response('{"category": "question", "topic": "", "priority": "normal", "urgency_score": 1, "summary": "", "custom_fields": {}}'),
        ),
    ]
    transport.handler = lambda payload: responses.pop(0)
    result = _client(transport, max_retries=2).generate(
        system="s", user="u", response_model=ClassificationContract
    )
    assert result.valid is True
    assert result.attempts == 2


def test_malformed_json_repairs_once() -> None:
    transport = _FakeTransport()
    responses = [
        _FakeResponse(200, _chat_response("sorry, not JSON")),
        _FakeResponse(
            200,
            _chat_response('{"category": "incident", "topic": "", "priority": "high", "urgency_score": 7, "summary": "", "custom_fields": {}}'),
        ),
    ]
    transport.handler = lambda payload: responses.pop(0)
    result = _client(transport, max_retries=3).generate(
        system="s", user="u", response_model=ClassificationContract
    )
    assert result.valid is True
    assert result.repair_attempted is True
    assert result.attempts == 2


def test_schema_invalid_not_retried() -> None:
    transport = _FakeTransport()
    # Valid JSON but missing required 'category'.
    transport.handler = lambda payload: _FakeResponse(
        200, _chat_response('{"topic": "refund"}')
    )
    result = _client(transport, max_retries=3).generate(
        system="s", user="u", response_model=ClassificationContract
    )
    assert result.valid is False
    assert result.attempts == 1
    assert result.repair_attempted is False


def test_exhausted_retries_returns_error() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(429, text="rate limit")
    result = _client(transport, max_retries=2).generate(
        system="s", user="u", response_model=ClassificationContract
    )
    assert result.valid is False
    assert result.attempts == 3  # initial + 2 retries
    assert result.error is not None


def test_structured_classifier_resolves_topic_and_fields() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200,
        _chat_response(
            '{"category": "question", "topic": "refund", "priority": "normal", '
            '"urgency_score": 3, "summary": "s", '
            '"custom_fields": {"17": "High"}}'
        ),
    )
    client = _client(transport)
    classifier = StructuredClassifier(client)

    topics = [{"id": 1, "name": "Refund", "status": "active"}]
    fields = [
        {"id": 17, "name": "priority", "type": "select", "options": "Low,High", "status": "active"}
    ]

    outcome = classifier.classify("Can I get a refund?", topics, fields)
    assert outcome.topic_id == 1
    assert outcome.topic_resolved is True
    assert outcome.topic == "Refund"
    assert outcome.custom_fields == {"17": "High"}


def test_structured_classifier_rejects_invalid_topic_and_foreign_field() -> None:
    transport = _FakeTransport()
    transport.handler = lambda payload: _FakeResponse(
        200,
        _chat_response(
            '{"category": "question", "topic": "made_up_topic", "priority": "normal", '
            '"urgency_score": 3, "summary": "s", '
            '"custom_fields": {"999": "x", "17": "InvalidOption"}}'
        ),
    )
    classifier = StructuredClassifier(_client(transport))

    topics = [{"id": 1, "name": "Refund", "status": "active"}]
    fields = [
        {"id": 17, "name": "priority", "type": "select", "options": "Low,High", "status": "active"}
    ]

    outcome = classifier.classify("hello", topics, fields)
    assert outcome.topic_resolved is False
    assert outcome.topic_id is None
    # Invalid select value + foreign field id both rejected.
    assert outcome.custom_fields == {}
