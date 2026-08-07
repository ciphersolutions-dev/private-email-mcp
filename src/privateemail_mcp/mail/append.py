"""Reliable IMAP APPEND for PrivateEmail Sent/Drafts archival.

aioimaplib APPEND is fragile against some servers (continuation/literal
timeouts). The agent-facing error ``OKKN5 APPEND Sent (\\Seen) {895}`` is the
string form of an aioimaplib CommandTimeout — not a real server rejection.

We archive with the stdlib ``imaplib`` client in a worker thread instead:
CRLF-normalized RFC822 bytes, quoted mailbox names, retries, and clear errors.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from privateemail_mcp.config import Config

logger = logging.getLogger("privateemail_mcp.append")


def normalize_rfc822_crlf(raw: bytes) -> bytes:
    """IMAP APPEND expects CRLF line endings in the message literal."""
    if not raw:
        return raw
    # Normalize any mix of CRLF / LF / CR to CRLF without doubling.
    text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return text.replace(b"\n", b"\r\n")


# Always quote common special-use folders for Open-Xchange / PrivateEmail.
SPECIAL_USE = {"Sent", "Drafts", "Trash", "Spam", "Junk", "Archive", "INBOX"}


def quote_mailbox(name: str) -> str:
    """Quote an IMAP mailbox name when needed."""
    name = name.strip()
    if not name:
        raise ValueError("Mailbox name is required")
    if name.startswith('"') and name.endswith('"'):
        return name
    if name in SPECIAL_USE or any(ch in name for ch in (' ', '"', '\\', '{')):
        escaped = name.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return name


def _append_sync(
    cfg: Config,
    raw_message: bytes,
    mailbox: str,
    flags: str | None,
) -> str:
    from privateemail_mcp.mail.transport import SyncImap4SSL, make_ssl_context, resolve_tls_hostname

    raw = normalize_rfc822_crlf(raw_message)
    mailbox_q = quote_mailbox(mailbox)
    flag_arg = flags
    if flag_arg is not None and not (flag_arg.startswith("(") and flag_arg.endswith(")")):
        flag_arg = f"({flag_arg})"

    timeout = min(cfg.connect_timeout, cfg.command_timeout)
    client = SyncImap4SSL(
        cfg.imap_host,
        cfg.imap_port,
        ssl_context=make_ssl_context(),
        timeout=timeout,
        tls_hostname=resolve_tls_hostname(cfg, for_imap=True),
    )
    try:
        typ, data = client.login(cfg.address, cfg.password)
        if typ != "OK":
            raise RuntimeError(f"IMAP login failed during APPEND: {data}")
        typ, data = client.append(mailbox_q, flag_arg, None, raw)
        if typ != "OK":
            raise RuntimeError(f"APPEND to {mailbox} failed: {typ} {data}")
        return "appended"
    finally:
        try:
            client.logout()
        except Exception:
            try:
                client.shutdown()
            except Exception:
                pass


async def append_with_retries(
    cfg: Config,
    raw_message: bytes,
    mailbox: str,
    *,
    flags: str | None = r"(\Seen)",
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> dict[str, Any]:
    """APPEND with retries. Raises RuntimeError if all attempts fail."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            status = await asyncio.to_thread(
                _append_sync, cfg, raw_message, mailbox, flags
            )
            return {
                "status": status,
                "mailbox": mailbox,
                "attempts": attempt,
            }
        except Exception as exc:
            last_error = exc
            logger.warning(
                "IMAP APPEND to %s failed (attempt %s/%s): %s",
                mailbox,
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                await asyncio.sleep(backoff_seconds * attempt)
    assert last_error is not None
    raise RuntimeError(
        f"IMAP APPEND to {mailbox} failed after {attempts} attempts: {last_error}"
    ) from last_error
