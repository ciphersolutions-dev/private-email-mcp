"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


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

    def validate(self) -> None:
        if not self.address:
            raise ValueError("PRIVATEEMAIL_ADDRESS is not set")
        if not self.password:
            raise ValueError("PRIVATEEMAIL_PASSWORD is not set")


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
    )


_cfg: Config | None = None


def get_config() -> Config:
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg
