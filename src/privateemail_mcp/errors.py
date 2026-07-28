"""Agent-friendly error mapping for MCP tools."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

from mcp.server.fastmcp.exceptions import ToolError

from privateemail_mcp.config import get_config

T = TypeVar("T")


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

    if "timeout" in lower or "timed out" in lower:
        return ToolError(
            f"PrivateEmail timed out while {action}. Retry with a smaller limit "
            "or narrow the search criteria."
        )

    if "no message data" in lower or "fetch" in lower and "failed" in lower:
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
