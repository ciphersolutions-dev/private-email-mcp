"""Agent-friendly error mapping for MCP tools."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

from mcp.server.fastmcp.exceptions import ToolError

from privateemail_mcp.config import get_config
from privateemail_mcp.mail.transport import is_loopback_host

T = TypeVar("T")

_NETWORK_HINT = (
    "Outbound IMAP/SMTP ports are often blocked on VPNs. "
    "If health_check keeps timing out, run scripts/mail-tunnel.sh "
    "(SSH LocalForward via a host that can reach mail.privateemail.com), "
    "then set PRIVATEEMAIL_IMAP_HOST=127.0.0.1 PRIVATEEMAIL_IMAP_PORT=21993 "
    "PRIVATEEMAIL_SMTP_HOST=127.0.0.1 PRIVATEEMAIL_SMTP_PORT=21465 "
    "PRIVATEEMAIL_TLS_HOSTNAME=mail.privateemail.com."
)


def validate_uid(uid: str) -> str:
    value = (uid or "").strip()
    if not value.isdigit():
        raise ToolError(
            f"Invalid IMAP UID '{uid}'. Use the numeric uid from list_emails, "
            "search_emails, or privateemail://inbox/recent."
        )
    return value


def validate_folder(folder: str) -> str:
    value = (folder or "").strip()
    if not value:
        raise ToolError("Folder name is required. Common values: INBOX, Sent, Drafts, Trash.")
    return value


def map_mail_error(exc: Exception, *, action: str) -> ToolError:
    message = str(exc).strip() or type(exc).__name__
    lower = message.lower()
    exc_name = type(exc).__name__.lower()

    if isinstance(exc, ValueError) and "PRIVATEEMAIL_" in message:
        return ToolError(f"Configuration error: {message}")

    if "login failed" in lower or "authentication failed" in lower:
        return ToolError(
            "PrivateEmail authentication failed. Check PRIVATEEMAIL_ADDRESS and "
            "PRIVATEEMAIL_PASSWORD, then retry health_check."
        )

    if "illegal in state" in lower:
        return ToolError(
            f"PrivateEmail IMAP state error while {action}. Retry the tool; "
            "this release uses one IMAP connection per call to avoid mailbox races."
        )

    # Must run before generic timeout matching - Sent archive errors often nest timeouts.
    if "saving a copy to the sent folder failed" in lower or (
        "smtp" in lower and "sent folder" in lower
    ):
        return ToolError(
            "PrivateEmail delivered the email over SMTP, but failed to archive it "
            f"in Sent after retries: {message}. Recipients still received it. "
            "Reconnect IMAP and retry only if you need the Sent copy repaired."
        )

    if "append" in lower and ("failed" in lower or "timeout" in lower or "timed out" in lower):
        return ToolError(
            f"PrivateEmail IMAP APPEND failed while {action}: {message}. "
            "This is usually a transient IMAP connection issue - retry the tool."
        )

    timed_out = (
        "timeout" in lower
        or "timed out" in lower
        or "timeout" in exc_name
        or isinstance(exc, TimeoutError)
    )
    conn_refused = "connection refused" in lower or "errno 111" in lower
    if timed_out or conn_refused:
        cfg = get_config()
        endpoint = f"{cfg.imap_host}:{cfg.imap_port}"
        if is_loopback_host(cfg.imap_host):
            return ToolError(
                f"PrivateEmail timed out while {action} via tunnel {endpoint}. "
                "Is scripts/mail-tunnel.sh still running? Restart the tunnel and retry."
            )
        return ToolError(
            f"PrivateEmail could not connect while {action} "
            f"(endpoint {endpoint}): {message}. {_NETWORK_HINT}"
        )

    if "no message data" in lower or ("fetch" in lower and "failed" in lower):
        uid_hint = ""
        m = re.search(r"uid\s*(\d+)", lower)
        if m:
            uid_hint = f" UID {m.group(1)} may no longer exist in that folder."
        return ToolError(
            f"Could not read the requested email while {action}.{uid_hint} "
            "Verify folder and uid, then retry."
        )

    if "select" in lower and "failed" in lower:
        return ToolError(
            f"Folder not found or not selectable while {action}. "
            "Use list_folders to confirm the exact folder name."
        )

    return ToolError(f"PrivateEmail error while {action}: {message}")


async def run_imap_tool(
    action: str,
    operation: Callable[..., Awaitable[T]],
    *args: object,
    **kwargs: object,
) -> T:
    """Validate config, open a short-lived IMAP session, and map failures."""
    get_config().validate()
    try:
        from privateemail_mcp.mail.imap_client import imap_session

        async with imap_session() as imap:
            return await operation(imap, *args, **kwargs)
    except ToolError:
        raise
    except Exception as exc:
        raise map_mail_error(exc, action=action) from exc
