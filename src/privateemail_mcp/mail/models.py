"""Email data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AttachmentMeta:
    filename: str
    content_type: str
    size: int
    part_index: int
    content_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmailSummary:
    uid: str
    folder: str
    subject: str
    from_addr: str
    to_addrs: list[str]
    date: str | None
    message_id: str | None
    flags: list[str]
    has_attachments: bool
    snippet: str = ""
    size: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmailDetail:
    uid: str
    folder: str
    subject: str
    from_addr: str
    to_addrs: list[str]
    cc_addrs: list[str]
    bcc_addrs: list[str]
    date: str | None
    message_id: str | None
    in_reply_to: str | None
    references: list[str]
    flags: list[str]
    text_body: str
    html_body: str
    attachments: list[AttachmentMeta] = field(default_factory=list)
    raw_headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
