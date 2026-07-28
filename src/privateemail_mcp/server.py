"""PrivateEmail MCP — mailbox tools, resources, and prompts for AI agents.

Session-scoped: every action runs while the MCP client is connected.
No background workers or durable schedulers.
"""

from __future__ import annotations

import json
import logging
from email.utils import parseaddr
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from pydantic import Field

from privateemail_mcp import __version__
from privateemail_mcp.config import get_config
from privateemail_mcp.mail.imap_client import get_imap, normalize_folder
from privateemail_mcp.mail.parsing import build_message
from privateemail_mcp.mail.smtp_client import get_smtp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("privateemail_mcp")

mcp = FastMCP(
    "privateemail",
    instructions=(
        "Namecheap PrivateEmail mailbox via IMAP/SMTP (mail.privateemail.com). "
        "Use tools to read, search, send, reply, organize mail. "
        "Read resources privateemail://account, privateemail://folders, "
        "privateemail://inbox/recent, privateemail://inbox/unread for context. "
        "Use prompts summarize_inbox, draft_reply, compose_email, triage_unread "
        "for common workflows. UIDs are IMAP UIDs within a folder."
    ),
)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _split_addrs(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _attachment_list(paths: str | None) -> list[dict[str, Any]] | None:
    if not paths:
        return None
    out = []
    for p in paths.split(","):
        p = p.strip()
        if p:
            out.append({"path": p, "filename": p.rsplit("/", 1)[-1]})
    return out or None


# ---------------------------------------------------------------------------
# Resources (read-only context for the model)
# ---------------------------------------------------------------------------


@mcp.resource("privateemail://account")
async def resource_account() -> str:
    """Configured PrivateEmail account metadata."""
    cfg = get_config()
    cfg.validate()
    return _json(
        {
            "address": cfg.address,
            "display_name": cfg.display_name,
            "imap": f"{cfg.imap_host}:{cfg.imap_port}",
            "smtp": f"{cfg.smtp_host}:{cfg.smtp_port}",
            "version": __version__,
        }
    )


@mcp.resource("privateemail://folders")
async def resource_folders() -> str:
    """IMAP folder tree."""
    get_config().validate()
    imap = await get_imap()
    return _json({"folders": await imap.list_folders()})


@mcp.resource("privateemail://inbox/recent")
async def resource_inbox_recent() -> str:
    """Newest 15 messages in INBOX (summaries)."""
    get_config().validate()
    imap = await get_imap()
    summaries = await imap.fetch_summaries("INBOX", limit=15)
    return _json({"emails": [s.to_dict() for s in summaries]})


@mcp.resource("privateemail://inbox/unread")
async def resource_inbox_unread() -> str:
    """Unread messages in INBOX (up to 25 summaries)."""
    get_config().validate()
    imap = await get_imap()
    summaries = await imap.fetch_summaries("INBOX", limit=25, unread_only=True)
    return _json({"emails": [s.to_dict() for s in summaries]})


@mcp.resource("privateemail://email/{folder}/{uid}")
async def resource_email(folder: str, uid: str) -> str:
    """Full message body for a folder + IMAP UID."""
    get_config().validate()
    imap = await get_imap()
    detail = await imap.fetch_email(folder, uid)
    return _json(detail.to_dict())


# ---------------------------------------------------------------------------
# Prompts (reusable workflows)
# ---------------------------------------------------------------------------


@mcp.prompt()
async def summarize_inbox(limit: int = 15) -> list[base.Message]:
    """Summarize recent INBOX mail and flag what needs action."""
    get_config().validate()
    imap = await get_imap()
    summaries = await imap.fetch_summaries("INBOX", limit=limit)
    payload = _json([s.to_dict() for s in summaries])
    return [
        base.UserMessage(
            f"Summarize these PrivateEmail INBOX messages. "
            f"Group by urgency, note unanswered threads, and list suggested next actions.\n\n{payload}"
        )
    ]


@mcp.prompt()
async def draft_reply(uid: str, folder: str = "INBOX", tone: str = "professional") -> list[base.Message]:
    """Draft a reply to a specific message (does not send)."""
    get_config().validate()
    imap = await get_imap()
    detail = await imap.fetch_email(folder, uid)
    return [
        base.UserMessage(
            f"Draft a {tone} reply to this email. Return subject + body only; do not send unless asked.\n\n"
            f"{_json(detail.to_dict())}"
        )
    ]


@mcp.prompt()
async def compose_email(
    goal: str,
    recipient: str,
    context: str = "",
) -> list[base.Message]:
    """Help compose a new outbound email (does not send)."""
    return [
        base.UserMessage(
            f"Compose an email to {recipient}.\n"
            f"Goal: {goal}\n"
            f"Extra context: {context or 'none'}\n\n"
            "Return: subject line, plain-text body, optional HTML body. "
            "Keep it concise. Do not send unless the user asks to use send_email."
        )
    ]


@mcp.prompt()
async def triage_unread(limit: int = 25) -> list[base.Message]:
    """Triage unread mail: archive, reply, or follow-up."""
    get_config().validate()
    imap = await get_imap()
    summaries = await imap.fetch_summaries("INBOX", limit=limit, unread_only=True)
    return [
        base.UserMessage(
            "Triage these unread PrivateEmail messages. For each: "
            "priority (high/med/low), recommended action "
            "(reply / archive / delete / wait), and a one-line reason.\n\n"
            f"{_json([s.to_dict() for s in summaries])}"
        )
    ]


# ---------------------------------------------------------------------------
# Tools — ops
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations={
        "title": "Health check",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def health_check() -> str:
    """Test IMAP and SMTP connectivity to mail.privateemail.com."""
    cfg = get_config()
    cfg.validate()
    imap = await get_imap()
    smtp = get_smtp()
    imap_result = await imap.health_check()
    try:
        smtp_result = await smtp.health_check()
    except Exception as e:
        smtp_result = {"ok": False, "error": str(e)}
    return _json({"version": __version__, "imap": imap_result, "smtp": smtp_result})


@mcp.tool(
    annotations={
        "title": "Account info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
async def account_info() -> str:
    """Show configured mailbox address and server endpoints."""
    cfg = get_config()
    cfg.validate()
    return _json(
        {
            "address": cfg.address,
            "display_name": cfg.display_name,
            "imap": f"{cfg.imap_host}:{cfg.imap_port}",
            "smtp": f"{cfg.smtp_host}:{cfg.smtp_port}",
            "version": __version__,
        }
    )


# ---------------------------------------------------------------------------
# Tools — read / search
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations={
        "title": "List folders",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def list_folders() -> str:
    """List IMAP folders in the PrivateEmail mailbox."""
    get_config().validate()
    imap = await get_imap()
    return _json({"folders": await imap.list_folders()})


@mcp.tool(
    annotations={
        "title": "List emails",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def list_emails(
    folder: Annotated[str, Field(description="IMAP folder, e.g. INBOX, Sent, Drafts")] = "INBOX",
    limit: Annotated[int, Field(ge=1, le=100, description="Max messages to return")] = 25,
    unread_only: Annotated[bool, Field(description="Only unread messages")] = False,
    since: Annotated[
        str | None, Field(description="Optional YYYY-MM-DD lower bound")
    ] = None,
) -> str:
    """List recent email summaries in a folder."""
    get_config().validate()
    imap = await get_imap()
    summaries = await imap.fetch_summaries(
        folder, limit=limit, unread_only=unread_only, since=since
    )
    return _json({"folder": normalize_folder(folder), "emails": [s.to_dict() for s in summaries]})


@mcp.tool(
    annotations={
        "title": "Search emails",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def search_emails(
    folder: Annotated[str, Field(description="IMAP folder")] = "INBOX",
    from_addr: Annotated[str | None, Field(description="From contains")] = None,
    to_addr: Annotated[str | None, Field(description="To contains")] = None,
    subject: Annotated[str | None, Field(description="Subject contains")] = None,
    body: Annotated[str | None, Field(description="Body contains")] = None,
    text: Annotated[str | None, Field(description="Anywhere in message")] = None,
    before: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    after: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    unread: Annotated[bool | None, Field(description="True=unread, False=read")] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
) -> str:
    """Search emails with IMAP criteria. Dates are YYYY-MM-DD."""
    get_config().validate()
    imap = await get_imap()
    uids = await imap.search(
        folder,
        from_addr=from_addr,
        to_addr=to_addr,
        subject=subject,
        body=body,
        text=text,
        before=before,
        after=after,
        unread=unread,
        limit=limit,
    )
    summaries = await imap.fetch_summaries(folder, uids=uids, limit=limit)
    return _json(
        {
            "folder": normalize_folder(folder),
            "count": len(summaries),
            "emails": [s.to_dict() for s in summaries],
        }
    )


@mcp.tool(
    annotations={
        "title": "Get email",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def get_email(
    uid: Annotated[str, Field(description="IMAP UID")],
    folder: Annotated[str, Field(description="IMAP folder")] = "INBOX",
) -> str:
    """Fetch full email by UID including text/html and attachment metadata."""
    get_config().validate()
    imap = await get_imap()
    return _json((await imap.fetch_email(folder, uid)).to_dict())


@mcp.tool(
    annotations={
        "title": "Get thread",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def get_thread(
    uid: Annotated[str, Field(description="IMAP UID of any message in the thread")],
    folder: Annotated[str, Field(description="IMAP folder")] = "INBOX",
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
) -> str:
    """Fetch a conversation thread related to the given message UID."""
    get_config().validate()
    imap = await get_imap()
    thread = await imap.get_thread(folder, uid, limit=limit)
    return _json({"folder": normalize_folder(folder), "messages": [m.to_dict() for m in thread]})


@mcp.tool(
    annotations={
        "title": "Download attachment",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def download_attachment(
    uid: Annotated[str, Field(description="IMAP UID")],
    part_index: Annotated[int, Field(ge=0, description="Attachment index from get_email")],
    folder: Annotated[str, Field(description="IMAP folder")] = "INBOX",
    save_path: Annotated[
        str | None, Field(description="If set, write file here instead of returning base64")
    ] = None,
) -> str:
    """Download an attachment by part_index from get_email."""
    get_config().validate()
    imap = await get_imap()
    return _json(await imap.download_attachment(folder, uid, part_index, save_path=save_path))


# ---------------------------------------------------------------------------
# Tools — write / manage
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations={
        "title": "Send email",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def send_email(
    to: Annotated[str, Field(description="Comma-separated recipients")],
    subject: Annotated[str, Field(description="Subject line", min_length=1)],
    text: Annotated[str | None, Field(description="Plain-text body")] = None,
    html: Annotated[str | None, Field(description="HTML body")] = None,
    cc: Annotated[str | None, Field(description="Comma-separated CC")] = None,
    bcc: Annotated[str | None, Field(description="Comma-separated BCC")] = None,
    reply_to: Annotated[str | None, Field(description="Reply-To address")] = None,
    in_reply_to: Annotated[str | None, Field(description="In-Reply-To Message-ID")] = None,
    references: Annotated[str | None, Field(description="Space-separated Message-IDs")] = None,
    attachment_paths: Annotated[
        str | None, Field(description="Comma-separated local file paths")
    ] = None,
) -> str:
    """Send an email via PrivateEmail SMTP. Prefer reply_email for threaded replies."""
    get_config().validate()
    if not text and not html:
        raise ValueError("Provide text and/or html body")
    refs = [r for r in (references or "").split() if r] or None
    smtp = get_smtp()
    result = await smtp.send_email(
        to=to,
        subject=subject,
        text=text,
        html=html,
        cc=cc,
        bcc=bcc,
        reply_to=reply_to,
        in_reply_to=in_reply_to,
        references=refs,
        attachments=_attachment_list(attachment_paths),
    )
    return _json(result)


@mcp.tool(
    annotations={
        "title": "Reply to email",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def reply_email(
    uid: Annotated[str, Field(description="IMAP UID to reply to")],
    text: Annotated[str | None, Field(description="Plain-text reply body")] = None,
    html: Annotated[str | None, Field(description="HTML reply body")] = None,
    folder: Annotated[str, Field(description="IMAP folder")] = "INBOX",
    reply_all: Annotated[bool, Field(description="Include original To/Cc")] = False,
) -> str:
    """Reply to an email by UID. Sets In-Reply-To and References for threading."""
    get_config().validate()
    if not text and not html:
        raise ValueError("Provide text and/or html body")
    imap = await get_imap()
    original = await imap.fetch_email(folder, uid)
    _, from_addr = parseaddr(original.from_addr)
    to = from_addr or original.from_addr
    cc = None
    if reply_all:
        cfg = get_config()
        others = []
        for a in original.to_addrs + original.cc_addrs:
            _, addr = parseaddr(a)
            if addr and addr.lower() != cfg.address.lower() and addr.lower() != (from_addr or "").lower():
                others.append(a)
        if others:
            cc = ", ".join(others)
    subj = original.subject or ""
    if not subj.lower().startswith("re:"):
        subj = f"Re: {subj}"
    refs = list(original.references or [])
    if original.message_id:
        refs.append(original.message_id)
    result = await get_smtp().send_email(
        to=to,
        subject=subj,
        text=text,
        html=html,
        cc=cc,
        in_reply_to=original.message_id,
        references=refs or None,
    )
    return _json({"replied_to_uid": uid, **result})


@mcp.tool(
    annotations={
        "title": "Forward email",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def forward_email(
    uid: Annotated[str, Field(description="IMAP UID to forward")],
    to: Annotated[str, Field(description="Forward recipient(s), comma-separated")],
    folder: Annotated[str, Field(description="IMAP folder")] = "INBOX",
    note: Annotated[str | None, Field(description="Optional note above forwarded content")] = None,
) -> str:
    """Forward an email by UID to a new recipient."""
    get_config().validate()
    imap = await get_imap()
    original = await imap.fetch_email(folder, uid)
    body = (note + "\n\n" if note else "") + (
        "---------- Forwarded message ----------\n"
        f"From: {original.from_addr}\n"
        f"Date: {original.date}\n"
        f"Subject: {original.subject}\n"
        f"To: {', '.join(original.to_addrs)}\n\n"
        f"{original.text_body}"
    )
    subj = original.subject or ""
    if not subj.lower().startswith("fwd:"):
        subj = f"Fwd: {subj}"
    result = await get_smtp().send_email(to=to, subject=subj, text=body)
    return _json({"forwarded_uid": uid, **result})


@mcp.tool(
    annotations={
        "title": "Save draft",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def save_draft(
    to: Annotated[str, Field(description="Comma-separated recipients")],
    subject: Annotated[str, Field(description="Subject")],
    text: Annotated[str | None, Field(description="Plain-text body")] = None,
    html: Annotated[str | None, Field(description="HTML body")] = None,
    cc: Annotated[str | None, Field(description="Comma-separated CC")] = None,
) -> str:
    """Save a draft into the Drafts IMAP folder."""
    cfg = get_config()
    cfg.validate()
    msg = build_message(
        from_addr=cfg.address,
        to=_split_addrs(to),
        subject=subject,
        text=text,
        html=html,
        cc=_split_addrs(cc),
        display_name=cfg.display_name or None,
    )
    imap = await get_imap()
    status = await imap.append_draft(msg.as_bytes())
    return _json({"status": status, "subject": subject, "to": to})


@mcp.tool(
    annotations={
        "title": "List drafts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def list_drafts(
    limit: Annotated[int, Field(ge=1, le=100)] = 25,
) -> str:
    """List messages in the Drafts folder."""
    get_config().validate()
    imap = await get_imap()
    summaries = await imap.fetch_summaries("Drafts", limit=limit)
    return _json({"emails": [s.to_dict() for s in summaries]})


@mcp.tool(
    annotations={
        "title": "Send draft",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def send_draft(
    uid: Annotated[str, Field(description="Draft IMAP UID")],
) -> str:
    """Send a draft by UID from Drafts, then move it to Trash."""
    get_config().validate()
    imap = await get_imap()
    detail = await imap.fetch_email("Drafts", uid)
    result = await get_smtp().send_email(
        to=detail.to_addrs or [""],
        subject=detail.subject,
        text=detail.text_body,
        html=detail.html_body or None,
        cc=", ".join(detail.cc_addrs) if detail.cc_addrs else None,
    )
    await imap.delete("Drafts", uid, expunge=False)
    return _json({"draft_uid": uid, **result})


@mcp.tool(
    annotations={
        "title": "Move email",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def move_email(
    uid: Annotated[str, Field(description="IMAP UID")],
    dest_folder: Annotated[str, Field(description="Destination folder")],
    folder: Annotated[str, Field(description="Source folder")] = "INBOX",
) -> str:
    """Move an email to another folder."""
    get_config().validate()
    imap = await get_imap()
    status = await imap.move(folder, uid, dest_folder)
    return _json({"uid": uid, "from": folder, "to": dest_folder, "status": status})


@mcp.tool(
    annotations={
        "title": "Copy email",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def copy_email(
    uid: Annotated[str, Field(description="IMAP UID")],
    dest_folder: Annotated[str, Field(description="Destination folder")],
    folder: Annotated[str, Field(description="Source folder")] = "INBOX",
) -> str:
    """Copy an email to another folder."""
    get_config().validate()
    imap = await get_imap()
    status = await imap.copy(folder, uid, dest_folder)
    return _json({"uid": uid, "status": status})


@mcp.tool(
    annotations={
        "title": "Delete email",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def delete_email(
    uid: Annotated[str, Field(description="IMAP UID")],
    folder: Annotated[str, Field(description="IMAP folder")] = "INBOX",
    expunge: Annotated[
        bool, Field(description="Permanently delete instead of moving to Trash")
    ] = False,
) -> str:
    """Delete an email (moves to Trash unless expunge=True or already in Trash)."""
    get_config().validate()
    imap = await get_imap()
    status = await imap.delete(folder, uid, expunge=expunge)
    return _json({"uid": uid, "status": status})


@mcp.tool(
    annotations={
        "title": "Mark email",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def mark_email(
    uid: Annotated[str, Field(description="IMAP UID")],
    folder: Annotated[str, Field(description="IMAP folder")] = "INBOX",
    read: Annotated[bool | None, Field(description="True=read, False=unread")] = None,
    flagged: Annotated[bool | None, Field(description="True=flag, False=unflag")] = None,
) -> str:
    """Mark email read/unread and/or flagged/unflagged."""
    get_config().validate()
    imap = await get_imap()
    status = await imap.mark(folder, uid, read=read, flagged=flagged)
    return _json({"uid": uid, "status": status, "read": read, "flagged": flagged})


@mcp.tool(
    annotations={
        "title": "Create folder",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def create_folder(
    name: Annotated[str, Field(description="New folder name", min_length=1)],
) -> str:
    """Create an IMAP folder."""
    get_config().validate()
    imap = await get_imap()
    return _json({"name": name, "status": await imap.create_folder(name)})


@mcp.tool(
    annotations={
        "title": "Rename folder",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def rename_folder(
    old_name: Annotated[str, Field(description="Current folder name")],
    new_name: Annotated[str, Field(description="New folder name")],
) -> str:
    """Rename an IMAP folder."""
    get_config().validate()
    imap = await get_imap()
    return _json(
        {
            "old": old_name,
            "new": new_name,
            "status": await imap.rename_folder(old_name, new_name),
        }
    )


@mcp.tool(
    annotations={
        "title": "Delete folder",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def delete_folder(
    name: Annotated[str, Field(description="Folder to delete")],
) -> str:
    """Delete an IMAP folder."""
    get_config().validate()
    imap = await get_imap()
    return _json({"name": name, "status": await imap.delete_folder(name)})


def main() -> None:
    cfg = get_config()
    try:
        cfg.validate()
    except ValueError as e:
        logger.error("%s", e)
        raise SystemExit(str(e)) from e
    logger.info("Starting PrivateEmail MCP v%s for %s", __version__, cfg.address)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
