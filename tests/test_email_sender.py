from __future__ import annotations

import pytest

from email_assistant.core.email_sender import send_reply, strip_subject_body_labels

ACCOUNT = {
    "address": "support@example.com",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "password": "pw",
}


class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sent = []
        self.started_tls = False
        _FakeSMTP.instances.append(self)

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *args) -> bool:  # noqa: ANN002
        return False

    def ehlo(self) -> None:
        pass

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def send_message(self, msg) -> None:  # noqa: ANN001
        self.sent.append(msg)


def test_send_reply_uses_starttls_on_587(monkeypatch) -> None:
    _FakeSMTP.instances = []
    monkeypatch.setattr(
        "email_assistant.core.email_sender.smtplib.SMTP", _FakeSMTP
    )

    send_reply(ACCOUNT, "to@example.com", "Hello", "Body text")

    assert len(_FakeSMTP.instances) == 1
    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.started_tls is True
    assert len(smtp.sent) == 1
    assert smtp.sent[0]["To"] == "to@example.com"
    assert smtp.sent[0]["Subject"] == "Re: Hello"


def test_send_reply_uses_ssl_on_465(monkeypatch) -> None:
    _FakeSMTP.instances = []
    monkeypatch.setattr(
        "email_assistant.core.email_sender.smtplib.SMTP_SSL", _FakeSMTP
    )

    send_reply({**ACCOUNT, "smtp_port": 465}, "to@example.com", "Re: Hi", "Body")

    assert len(_FakeSMTP.instances) == 1
    assert _FakeSMTP.instances[0].port == 465
    assert _FakeSMTP.instances[0].sent[0]["Subject"] == "Re: Hi"


def test_send_reply_respects_smtp_security_setting(monkeypatch) -> None:
    # Explicit starttls on a non-465 port.
    _FakeSMTP.instances = []
    monkeypatch.setattr("email_assistant.core.email_sender.smtplib.SMTP", _FakeSMTP)
    send_reply(
        {**ACCOUNT, "smtp_security": "starttls"},
        "to@example.com",
        "Hi",
        "Body",
    )
    assert _FakeSMTP.instances[0].started_tls is True

    # Explicit SSL on a non-465 port must use SMTP_SSL, not the port heuristic.
    _FakeSMTP.instances = []
    monkeypatch.setattr(
        "email_assistant.core.email_sender.smtplib.SMTP_SSL", _FakeSMTP
    )
    send_reply(
        {**ACCOUNT, "smtp_port": 587, "smtp_security": "ssl"},
        "to@example.com",
        "Hi",
        "Body",
    )
    assert len(_FakeSMTP.instances) == 1
    assert _FakeSMTP.instances[0].port == 587


def test_send_reply_unencrypted_requires_explicit_none(monkeypatch) -> None:
    _FakeSMTP.instances = []
    monkeypatch.setattr("email_assistant.core.email_sender.smtplib.SMTP", _FakeSMTP)
    send_reply(
        {**ACCOUNT, "smtp_security": "none"}, "to@example.com", "Hi", "Body"
    )
    assert _FakeSMTP.instances[0].started_tls is False

    # Unknown values fall back to the port heuristic (587 -> starttls).
    _FakeSMTP.instances = []
    send_reply(
        {**ACCOUNT, "smtp_security": "bogus"}, "to@example.com", "Hi", "Body"
    )
    assert _FakeSMTP.instances[0].started_tls is True


def test_send_reply_missing_address_raises() -> None:
    with pytest.raises(ValueError):
        send_reply({**ACCOUNT, "address": ""}, "to@example.com", "Hi", "Body")

    with pytest.raises(ValueError):
        send_reply({**ACCOUNT, "smtp_host": ""}, "to@example.com", "Hi", "Body")


def test_strip_labels_from_legacy_draft() -> None:
    legacy = (
        "Subject: Re: Hello\n"
        "\n"
        "Body:  \n"
        "Dear Jacky,\n"
        "\n"
        "Thanks for reaching out.\n"
        "\n"
        "Best regards,\n"
        "Support"
    )
    assert strip_subject_body_labels(legacy) == (
        "Dear Jacky,\n"
        "\n"
        "Thanks for reaching out.\n"
        "\n"
        "Best regards,\n"
        "Support"
    )


def test_strip_labels_keeps_plain_body() -> None:
    plain = "Dear Jacky,\n\nThanks!\n\nBest regards,\nSupport"
    assert strip_subject_body_labels(plain) == plain
