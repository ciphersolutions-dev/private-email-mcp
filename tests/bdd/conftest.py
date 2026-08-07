"""Shared BDD fixtures and context for PrivateEmail MCP acceptance tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class BddContext:
    env_backup: dict[str, str | None] = field(default_factory=dict)
    error: Exception | None = None
    result: Any = None
    raw_bytes: bytes | None = None
    normalized: bytes | None = None
    expected_crlf: bytes | None = None
    mail_failure: str | None = None
    mail_action: str | None = None
    agent_error: str | None = None
    original_subject: str | None = None
    prepared_subject: str | None = None
    email_detail: Any = None
    prompt_payload: dict[str, Any] | None = None
    html: str | None = None
    plain: str | None = None
    config: Any = None
    tools: set[str] = field(default_factory=set)
    prompts: set[str] = field(default_factory=set)
    smtp_ok: bool = True
    append_fail: bool = False
    append_succeed_on: int = 1


@pytest.fixture
def ctx() -> BddContext:
    return BddContext()


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure config tests do not leak real mailbox credentials."""
    keys = [
        "PRIVATEEMAIL_ADDRESS",
        "PRIVATEEMAIL_PASSWORD",
        "PRIVATEEMAIL_DISPLAY_NAME",
        "PRIVATEEMAIL_IMAP_HOST",
        "PRIVATEEMAIL_IMAP_PORT",
        "PRIVATEEMAIL_SMTP_HOST",
        "PRIVATEEMAIL_SMTP_PORT",
        "PRIVATEEMAIL_MAX_ATTACHMENT_BYTES",
        "PRIVATEEMAIL_CONNECT_TIMEOUT",
        "PRIVATEEMAIL_COMMAND_TIMEOUT",
        "PRIVATEEMAIL_TLS_HOSTNAME",
        "PRIVATEEMAIL_TUNNEL_SSH",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch
