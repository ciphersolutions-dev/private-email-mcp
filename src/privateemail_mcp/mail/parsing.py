"""MIME parsing helpers."""

from __future__ import annotations

import email
import email.policy
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup

from .models import AttachmentMeta, EmailDetail, EmailSummary


def decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def addresses_from_header(msg: Message, name: str) -> list[str]:
    raw = msg.get_all(name, [])
    if not raw:
        return []
    pairs = getaddresses([decode_mime_header(v) for v in raw])
    result: list[str] = []
    for name_part, addr in pairs:
        if not addr:
            continue
        if name_part:
            result.append(f"{name_part} <{addr}>")
        else:
            result.append(addr)
    return result


def first_address(msg: Message, name: str) -> str:
    addrs = addresses_from_header(msg, name)
    return addrs[0] if addrs else ""


def format_date(msg: Message) -> str | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        return decode_mime_header(raw)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def extract_bodies(msg: Message) -> tuple[str, str]:
    text_body = ""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", "")).lower()
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and not text_body:
                text_body = decoded
            elif ctype == "text/html" and not html_body:
                html_body = decoded
    else:
        ctype = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
            if payload is not None:
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if ctype == "text/html":
                    html_body = decoded
                else:
                    text_body = decoded
        except Exception:
            pass
    if not text_body and html_body:
        text_body = html_to_text(html_body)
    return text_body, html_body


def extract_attachments(msg: Message) -> list[AttachmentMeta]:
    attachments: list[AttachmentMeta] = []
    idx = 0
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        disp = str(part.get("Content-Disposition", "")).lower()
        cid = part.get("Content-ID")
        is_attach = bool(filename) or "attachment" in disp
        if not is_attach:
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            AttachmentMeta(
                filename=decode_mime_header(filename) or f"attachment-{idx}",
                content_type=part.get_content_type(),
                size=len(payload),
                part_index=idx,
                content_id=cid.strip("<>") if cid else None,
            )
        )
        idx += 1
    return attachments


def get_attachment_bytes(msg: Message, part_index: int) -> tuple[str, str, bytes]:
    idx = 0
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        disp = str(part.get("Content-Disposition", "")).lower()
        is_attach = bool(filename) or "attachment" in disp
        if not is_attach:
            continue
        if idx == part_index:
            payload = part.get_payload(decode=True) or b""
            return (
                decode_mime_header(filename) or f"attachment-{idx}",
                part.get_content_type(),
                payload,
            )
        idx += 1
    raise ValueError(f"Attachment part_index {part_index} not found")


def _guess_has_attachments(msg: Message) -> bool:
    ctype = (msg.get_content_type() or "").lower()
    if ctype.startswith("multipart/"):
        return ctype not in {"multipart/alternative", "multipart/related"}
    disp = str(msg.get("Content-Disposition", "")).lower()
    return "attachment" in disp


def parse_message_bytes(
    raw: bytes,
    *,
    uid: str,
    folder: str,
    flags: list[str] | None = None,
    include_body: bool = True,
    snippet_text: str | None = None,
) -> EmailDetail:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    if include_body:
        text_body, html_body = extract_bodies(msg)
        attachments = extract_attachments(msg)
    else:
        text_body = snippet_text or ""
        html_body = ""
        attachments = []
    refs_raw = decode_mime_header(msg.get("References"))
    references = [r for r in refs_raw.replace(",", " ").split() if r] if refs_raw else []
    headers: dict[str, str] = {}
    for k, v in msg.items():
        headers[k] = decode_mime_header(v)
    return EmailDetail(
        uid=uid,
        folder=folder,
        subject=decode_mime_header(msg.get("Subject")),
        from_addr=first_address(msg, "From"),
        to_addrs=addresses_from_header(msg, "To"),
        cc_addrs=addresses_from_header(msg, "Cc"),
        bcc_addrs=addresses_from_header(msg, "Bcc"),
        date=format_date(msg),
        message_id=msg.get("Message-ID"),
        in_reply_to=msg.get("In-Reply-To"),
        references=references,
        flags=flags or [],
        text_body=text_body,
        html_body=html_body,
        attachments=attachments,
        raw_headers=headers if include_body else {},
    )


def summary_from_detail(
    detail: EmailDetail,
    snippet_len: int = 160,
    *,
    has_attachments: bool | None = None,
) -> EmailSummary:
    snippet = (detail.text_body or "").replace("\n", " ").strip()
    if len(snippet) > snippet_len:
        snippet = snippet[: snippet_len - 1] + "…"
    attachment_flag = has_attachments if has_attachments is not None else bool(detail.attachments)
    return EmailSummary(
        uid=detail.uid,
        folder=detail.folder,
        subject=detail.subject,
        from_addr=detail.from_addr,
        to_addrs=detail.to_addrs,
        date=detail.date,
        message_id=detail.message_id,
        flags=detail.flags,
        has_attachments=attachment_flag,
        snippet=snippet,
    )


def parse_flags(flag_str: str | bytes | list | None) -> list[str]:
    if flag_str is None:
        return []
    if isinstance(flag_str, list):
        return [str(f).strip("\\") for f in flag_str]
    if isinstance(flag_str, bytes):
        flag_str = flag_str.decode("utf-8", errors="replace")
    parts = str(flag_str).replace("(", " ").replace(")", " ").split()
    return [p.lstrip("\\") for p in parts if p]


def build_message(
    *,
    from_addr: str,
    to: list[str],
    subject: str,
    text: str | None = None,
    html: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to: str | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
    display_name: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    from_header = f"{display_name} <{from_addr}>" if display_name else from_addr
    msg["From"] = from_header
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = " ".join(references)

    if html and text:
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
    elif html:
        msg.set_content(html_to_text(html))
        msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(text or "")

    for att in attachments or []:
        filename = att.get("filename") or "attachment"
        content_type = att.get("content_type") or "application/octet-stream"
        data = att.get("data")
        if data is None and "path" in att:
            with open(att["path"], "rb") as f:
                data = f.read()
        if isinstance(data, str):
            import base64

            data = base64.b64decode(data)
        if not isinstance(data, (bytes, bytearray)):
            raise ValueError(f"Attachment {filename} missing binary data")
        maintype, _, subtype = content_type.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            bytes(data),
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )
    return msg
