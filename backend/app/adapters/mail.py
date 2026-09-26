"""Mail transports. `file` writes RFC 5322 messages to disk (development);
`smtp` sends. Both raise on failure so the worker can record and retry."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Protocol

from email_validator import EmailNotValidError, validate_email

from app.config import get_settings


class MailTransport(Protocol):
    def send(self, to: str, subject: str, body: str) -> str: ...


def _build(to: str, subject: str, body: str) -> EmailMessage:
    try:
        # `.test` (RFC 2606) is accepted outside production so demo data can be delivered to the outbox.
        validate_email(to, check_deliverability=False, test_environment=not get_settings().is_production)
    except EmailNotValidError as exc:
        raise ValueError(f"invalid recipient address: {exc}") from exc
    msg = EmailMessage()
    msg["From"] = get_settings().mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain="tender.kortexd.com")
    msg.set_content(body)
    return msg


class FileMailTransport:
    def __init__(self, directory: str):
        self.directory = Path(directory)

    def send(self, to: str, subject: str, body: str) -> str:
        msg = _build(to, subject, body)
        self.directory.mkdir(parents=True, exist_ok=True)
        name = msg["Message-ID"].strip("<>").replace("@", "_") + ".eml"
        (self.directory / name).write_bytes(bytes(msg))
        return msg["Message-ID"]


class SmtpMailTransport:
    def __init__(self, host: str, port: int, username: str, password: str, starttls: bool):
        self.host, self.port, self.username, self.password, self.starttls = host, port, username, password, starttls

    def send(self, to: str, subject: str, body: str) -> str:
        msg = _build(to, subject, body)
        with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
            if self.starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)
        return msg["Message-ID"]


_transport: MailTransport | None = None


def get_mail_transport() -> MailTransport:
    global _transport
    if _transport is None:
        s = get_settings()
        if s.mail_backend == "smtp":
            _transport = SmtpMailTransport(s.smtp_host, s.smtp_port, s.smtp_username, s.smtp_password, s.smtp_starttls)
        else:
            _transport = FileMailTransport(s.mail_outbox_dir)
    return _transport


def set_mail_transport(transport: MailTransport | None) -> None:
    global _transport
    _transport = transport
