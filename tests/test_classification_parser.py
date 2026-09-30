from __future__ import annotations

from email_assistant.core.classification_parser import parse_classification

JSON = '{"category": "spam", "topic": "phishing_alert", "priority": "low", "summary": "A suspicious email", "custom": {}}'

PYTHON_LITERAL = (
    "category='spam' topic='phishing_alert' priority='low' "
    "summary='A suspicious email' custom={}"
)


def test_parse_json() -> None:
    result = parse_classification(JSON)
    assert result is not None
    assert result.category == "spam"
    assert result.topic == "phishing_alert"
    assert result.priority == "low"


def test_parse_json_with_code_fence() -> None:
    result = parse_classification(f"```json\n{JSON}\n```")
    assert result is not None
    assert result.category == "spam"


def test_parse_python_literal() -> None:
    result = parse_classification(PYTHON_LITERAL)
    assert result is not None
    assert result.category == "spam"
    assert result.topic == "phishing_alert"
    assert result.priority == "low"
    assert result.custom == {}


def test_parse_garbage_returns_none() -> None:
    assert parse_classification("") is None
    assert parse_classification("I'm sorry, I can't do that.") is None
    assert parse_classification("not a classification") is None


def test_parse_json_embedded_in_text() -> None:
    text = f'Here is the answer: {JSON} thanks'
    result = parse_classification(text)
    assert result is not None
    assert result.category == "spam"
