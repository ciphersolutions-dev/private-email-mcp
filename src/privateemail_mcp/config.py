"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Config:
    address: str
    password: str
    display_name: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    max_attachment_bytes: int
    # Fail fast on blocked VPN/firewall ports instead of hanging for a minute.
    connect_timeout: float
    # Per-command IMAP/SMTP timeout after the TCP session is up.
    command_timeout: float
    # TLS SNI / cert hostname when IMAP/SMTP host is a tunnel (127.0.0.1).
    tls_hostname: str

    def validate(self) -> None:
        if not self.address:
            raise ValueError("PRIVATEEMAIL_ADDRESS is not set")
        if not self.password:
            raise ValueError("PRIVATEEMAIL_PASSWORD is not set")
        if not self.imap_host:
            raise ValueError("PRIVATEEMAIL_IMAP_HOST is not set")
        if not self.smtp_host:
            raise ValueError("PRIVATEEMAIL_SMTP_HOST is not set")
        if self.imap_port <= 0:
            raise ValueError("PRIVATEEMAIL_IMAP_PORT must be a positive integer")
        if self.smtp_port <= 0:
            raise ValueError("PRIVATEEMAIL_SMTP_PORT must be a positive integer")
        if self.max_attachment_bytes <= 0:
            raise ValueError("PRIVATEEMAIL_MAX_ATTACHMENT_BYTES must be a positive integer")
        if self.connect_timeout <= 0:
            raise ValueError("PRIVATEEMAIL_CONNECT_TIMEOUT must be a positive number")
        if self.command_timeout <= 0:
            raise ValueError("PRIVATEEMAIL_COMMAND_TIMEOUT must be a positive number")


def load_config() -> Config:
    return Config(
        address=os.getenv("PRIVATEEMAIL_ADDRESS", "").strip(),
        password=os.getenv("PRIVATEEMAIL_PASSWORD", ""),
        display_name=os.getenv("PRIVATEEMAIL_DISPLAY_NAME", "").strip(),
        imap_host=os.getenv("PRIVATEEMAIL_IMAP_HOST", "mail.privateemail.com").strip(),
        imap_port=_int("PRIVATEEMAIL_IMAP_PORT", 993),
        smtp_host=os.getenv("PRIVATEEMAIL_SMTP_HOST", "mail.privateemail.com").strip(),
        smtp_port=_int("PRIVATEEMAIL_SMTP_PORT", 465),
        max_attachment_bytes=_int("PRIVATEEMAIL_MAX_ATTACHMENT_BYTES", 10 * 1024 * 1024),
        connect_timeout=_float("PRIVATEEMAIL_CONNECT_TIMEOUT", 12.0),
        command_timeout=_float("PRIVATEEMAIL_COMMAND_TIMEOUT", 30.0),
        tls_hostname=os.getenv("PRIVATEEMAIL_TLS_HOSTNAME", "").strip(),
    )


def get_config() -> Config:
    return load_config()
