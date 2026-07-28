"""IMAP client for PrivateEmail (mail.privateemail.com)."""

from __future__ import annotations

import asyncio
import email
import email.policy
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator

import aioimaplib

from privateemail_mcp.config import Config, get_config
from privateemail_mcp.mail.models import EmailDetail, EmailSummary
from privateemail_mcp.mail.parsing import (
    get_attachment_bytes,
    parse_flags,
    parse_message_bytes,
    summary_from_detail,
)

logger = logging.getLogger("privateemail_mcp.imap")

# Folder names commonly used by Open-Xchange / PrivateEmail
SPECIAL_FOLDERS = {
    "inbox": "INBOX",
    "sent": "Sent",
    "drafts": "Drafts",
    "trash": "Trash",
    "spam": "Spam",
    "junk": "Junk",
    "archive": "Archive",
}


def normalize_folder(folder: str) -> str:
    key = folder.strip().lower()
    return SPECIAL_FOLDERS.get(key, folder)


class ImapClient:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or get_config()
        self._client: aioimaplib.IMAP4_SSL | None = None

    async def connect(self) -> aioimaplib.IMAP4_SSL:
        if self._client is not None and self._client.get_state() != "LOGOUT":
            return self._client
        client = aioimaplib.IMAP4_SSL(host=self.cfg.imap_host, port=self.cfg.imap_port, timeout=60)
        await client.wait_hello_from_server()
        resp = await client.login(self.cfg.address, self.cfg.password)
        if resp.result != "OK":
            raise RuntimeError(f"IMAP login failed: {resp.lines}")
        self._client = client
        return client

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.logout()
        except Exception:
            pass
        self._client = None

    @asynccontextmanager
    async def session(self) -> AsyncIterator[aioimaplib.IMAP4_SSL]:
        client = await self.connect()
        try:
            yield client
        finally:
            # Keep connection for reuse within short bursts; caller may close.
            pass

    async def list_folders(self) -> list[dict[str, Any]]:
        client = await self.connect()
        resp = await client.list('""', "*")
        if resp.result != "OK":
            raise RuntimeError(f"LIST failed: {resp.lines}")
        folders: list[dict[str, Any]] = []
        for line in resp.lines:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            # Typical: (\HasNoChildren) "/" "INBOX"
            m = re.search(r'\(([^)]*)\)\s+"([^"]*)"\s+(.+)$', line)
            if not m:
                continue
            flags = [f.lstrip("\\") for f in m.group(1).split() if f]
            delim = m.group(2)
            name = m.group(3).strip().strip('"')
            folders.append({"name": name, "delimiter": delim, "flags": flags})
        return folders

    async def _select(self, folder: str, readonly: bool = True) -> aioimaplib.IMAP4_SSL:
        client = await self.connect()
        folder = normalize_folder(folder)
        # aioimaplib only transitions to SELECTED via select(); examine() does not
        # update client state, so SEARCH would fail with "illegal in state AUTH".
        _ = readonly
        resp = await client.select(folder)
        if resp.result != "OK":
            raise RuntimeError(f"SELECT {folder} failed: {resp.lines}")
        return client

    async def search(
        self,
        folder: str = "INBOX",
        *,
        from_addr: str | None = None,
        to_addr: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        before: str | None = None,
        after: str | None = None,
        unread: bool | None = None,
        has_attachment: bool | None = None,
        text: str | None = None,
        limit: int = 50,
    ) -> list[str]:
        client = await self._select(folder, readonly=True)
        criteria: list[str] = []
        if unread is True:
            criteria.append("UNSEEN")
        elif unread is False:
            criteria.append("SEEN")
        if from_addr:
            criteria.extend(["FROM", self._quote(from_addr)])
        if to_addr:
            criteria.extend(["TO", self._quote(to_addr)])
        if subject:
            criteria.extend(["SUBJECT", self._quote(subject)])
        if body:
            criteria.extend(["BODY", self._quote(body)])
        if text:
            criteria.extend(["TEXT", self._quote(text)])
        if before:
            criteria.extend(["BEFORE", self._imap_date(before)])
        if after:
            criteria.extend(["SINCE", self._imap_date(after)])
        # HEADER Content-Type for attachments is unreliable; skip strict IMAP filter
        if not criteria:
            criteria = ["ALL"]
        # aioimaplib uid_search(*criteria) — pass tokens separately
        resp = await client.uid_search(*criteria, charset=None)
        if resp.result != "OK":
            raise RuntimeError(f"SEARCH failed: {resp.lines}")
        uids = self._parse_uid_list(resp.lines)
        _ = has_attachment  # reserved for client-side filter later
        uids = uids[-limit:] if limit else uids
        uids.reverse()  # newest first typically at end
        return uids

    @staticmethod
    def _quote(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _imap_date(value: str) -> str:
        # Accept ISO date or datetime; IMAP wants DD-Mon-YYYY
        raw = value.strip()
        try:
            if "T" in raw:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            else:
                dt = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Invalid date '{value}': use YYYY-MM-DD") from e
        return dt.strftime("%d-%b-%Y")

    @staticmethod
    def _parse_uid_list(lines: list) -> list[str]:
        uids: list[str] = []
        for line in lines:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            # Skip OK lines
            if not line or line.startswith("OK") or "SEARCH" in line.upper() and not any(c.isdigit() for c in line):
                # Prefer numeric tokens
                pass
            for tok in str(line).split():
                if tok.isdigit():
                    uids.append(tok)
        # Deduplicate preserving order
        seen: set[str] = set()
        out: list[str] = []
        for u in uids:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    async def fetch_summaries(
        self,
        folder: str = "INBOX",
        *,
        uids: list[str] | None = None,
        limit: int = 25,
        unread_only: bool = False,
        since: str | None = None,
    ) -> list[EmailSummary]:
        if uids is None:
            uids = await self.search(
                folder,
                unread=True if unread_only else None,
                after=since,
                limit=limit,
            )
        else:
            uids = uids[:limit]
        results: list[EmailSummary] = []
        for uid in uids:
            try:
                detail = await self.fetch_email(folder, uid, include_body=False)
                results.append(summary_from_detail(detail))
            except Exception as e:
                logger.warning("Failed to fetch uid %s: %s", uid, e)
        return results

    async def fetch_email(
        self,
        folder: str,
        uid: str,
        *,
        include_body: bool = True,
    ) -> EmailDetail:
        client = await self._select(folder, readonly=True)
        # BODY.PEEK[] avoids setting \Seen
        fetch_items = "(FLAGS BODY.PEEK[])" if include_body else "(FLAGS BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.500>)"
        # Always fetch full for reliable parsing of structure
        resp = await client.uid("fetch", uid, "(FLAGS BODY.PEEK[])")
        if resp.result != "OK":
            raise RuntimeError(f"FETCH {uid} failed: {resp.lines}")
        raw, flags = self._extract_fetch_payload(resp.lines)
        if raw is None:
            raise RuntimeError(f"No message data for uid {uid}")
        return parse_message_bytes(raw, uid=uid, folder=normalize_folder(folder), flags=flags)

    @staticmethod
    def _extract_fetch_payload(lines: list) -> tuple[bytes | None, list[str]]:
        flags: list[str] = []
        chunks: list[bytes] = []
        for line in lines:
            # aioimaplib returns message bodies as bytearray
            if isinstance(line, (bytes, bytearray)):
                data = bytes(line)
                text_try = None
                try:
                    text_try = data.decode("utf-8")
                except Exception:
                    chunks.append(data)
                    continue
                # Meta / status lines from the server (not RFC822)
                if (
                    "FETCH (" in text_try
                    or text_try.startswith("FLAGS")
                    or text_try.startswith("Fetch completed")
                    or text_try.startswith("OK ")
                    or (len(data) < 200 and "BODY" in text_try.upper() and "{" in text_try)
                ):
                    m = re.search(r"FLAGS\s*\(([^)]*)\)", text_try)
                    if m:
                        flags = parse_flags(m.group(1))
                    continue
                if data.strip() in (b")", b""):
                    continue
                chunks.append(data)
            else:
                s = str(line)
                if "FLAGS" in s:
                    m = re.search(r"FLAGS\s*\(([^)]*)\)", s)
                    if m:
                        flags = parse_flags(m.group(1))
        if not chunks:
            return None, flags
        # Prefer the largest chunk that looks like an email
        emailish = [
            c
            for c in chunks
            if b"\n" in c and (b"From:" in c[:4000] or b"Subject:" in c[:4000] or b"Return-Path:" in c[:4000])
        ]
        raw = max(emailish or chunks, key=len)
        return raw, flags

    async def get_thread(self, folder: str, uid: str, limit: int = 50) -> list[EmailDetail]:
        root = await self.fetch_email(folder, uid)
        message_ids: set[str] = set()
        if root.message_id:
            message_ids.add(root.message_id.strip())
        if root.in_reply_to:
            message_ids.add(root.in_reply_to.strip())
        for r in root.references:
            message_ids.add(r.strip())

        # Search by subject as fallback thread key
        subject = root.subject or ""
        clean = re.sub(r"^(re|fw|fwd)\s*:\s*", "", subject, flags=re.I).strip()
        candidates = await self.search(folder, subject=clean or subject, limit=limit)
        thread: list[EmailDetail] = []
        for cuid in candidates:
            try:
                detail = await self.fetch_email(folder, cuid)
            except Exception:
                continue
            mid = (detail.message_id or "").strip()
            irt = (detail.in_reply_to or "").strip()
            refs = {r.strip() for r in detail.references}
            related = False
            if mid and mid in message_ids:
                related = True
            if irt and irt in message_ids:
                related = True
            if refs & message_ids:
                related = True
            if not message_ids and clean and clean.lower() in (detail.subject or "").lower():
                related = True
            if related:
                thread.append(detail)
                if mid:
                    message_ids.add(mid)
                if irt:
                    message_ids.add(irt)
                message_ids |= refs
        thread.sort(key=lambda d: d.date or "")
        return thread

    async def download_attachment(
        self,
        folder: str,
        uid: str,
        part_index: int,
        *,
        save_path: str | None = None,
    ) -> dict[str, Any]:
        client = await self._select(folder, readonly=True)
        resp = await client.uid("fetch", uid, "(BODY.PEEK[])")
        if resp.result != "OK":
            raise RuntimeError(f"FETCH failed: {resp.lines}")
        raw, _ = self._extract_fetch_payload(resp.lines)
        if raw is None:
            raise RuntimeError("No message data")
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        filename, content_type, data = get_attachment_bytes(msg, part_index)
        max_bytes = self.cfg.max_attachment_bytes
        if len(data) > max_bytes:
            raise ValueError(
                f"Attachment {filename} is {len(data)} bytes; max is {max_bytes}. "
                "Increase PRIVATEEMAIL_MAX_ATTACHMENT_BYTES or save via a smaller file."
            )
        import base64

        result: dict[str, Any] = {
            "filename": filename,
            "content_type": content_type,
            "size": len(data),
        }
        if save_path:
            with open(save_path, "wb") as f:
                f.write(data)
            result["saved_to"] = save_path
        else:
            result["data_base64"] = base64.b64encode(data).decode("ascii")
        return result

    async def mark(
        self,
        folder: str,
        uid: str,
        *,
        read: bool | None = None,
        flagged: bool | None = None,
    ) -> str:
        client = await self._select(folder, readonly=False)
        ops: list[str] = []
        if read is True:
            ops.append(r"+FLAGS (\Seen)")
        elif read is False:
            ops.append(r"-FLAGS (\Seen)")
        if flagged is True:
            ops.append(r"+FLAGS (\Flagged)")
        elif flagged is False:
            ops.append(r"-FLAGS (\Flagged)")
        if not ops:
            return "no-op"
        for op in ops:
            # IMAP: UID STORE <uid> +FLAGS (\Seen)
            flag_op, flag_list = op.split(" ", 1)
            resp = await client.uid("store", uid, flag_op, flag_list)
            if resp.result != "OK":
                raise RuntimeError(f"STORE failed: {resp.lines}")
        return "ok"

    async def move(self, folder: str, uid: str, dest: str) -> str:
        client = await self._select(folder, readonly=False)
        dest = normalize_folder(dest)
        # Try MOVE extension; fall back to COPY+DELETE
        try:
            resp = await client.uid("move", uid, dest)
            if resp.result == "OK":
                return "moved"
        except Exception:
            pass
        resp = await client.uid("copy", uid, dest)
        if resp.result != "OK":
            raise RuntimeError(f"COPY failed: {resp.lines}")
        await client.uid("store", uid, "+FLAGS", r"(\Deleted)")
        await client.expunge()
        return "copied-and-deleted"

    async def copy(self, folder: str, uid: str, dest: str) -> str:
        client = await self._select(folder, readonly=False)
        dest = normalize_folder(dest)
        resp = await client.uid("copy", uid, dest)
        if resp.result != "OK":
            raise RuntimeError(f"COPY failed: {resp.lines}")
        return "copied"

    async def delete(self, folder: str, uid: str, *, expunge: bool = False) -> str:
        trash = "Trash"
        if normalize_folder(folder).lower() == "trash" or expunge:
            client = await self._select(folder, readonly=False)
            resp = await client.uid("store", uid, "+FLAGS", r"(\Deleted)")
            if resp.result != "OK":
                raise RuntimeError(f"STORE delete failed: {resp.lines}")
            await client.expunge()
            return "expunged"
        await self.move(folder, uid, trash)
        return "moved-to-trash"

    async def create_folder(self, name: str) -> str:
        client = await self.connect()
        resp = await client.create(name)
        if resp.result != "OK":
            raise RuntimeError(f"CREATE failed: {resp.lines}")
        return "created"

    async def rename_folder(self, old: str, new: str) -> str:
        client = await self.connect()
        resp = await client.rename(old, new)
        if resp.result != "OK":
            raise RuntimeError(f"RENAME failed: {resp.lines}")
        return "renamed"

    async def delete_folder(self, name: str) -> str:
        client = await self.connect()
        resp = await client.delete(name)
        if resp.result != "OK":
            raise RuntimeError(f"DELETE folder failed: {resp.lines}")
        return "deleted"

    async def append_message(
        self,
        raw_message: bytes,
        folder: str,
        flags: str = r"(\Seen)",
    ) -> str:
        """APPEND a raw RFC822 message into an IMAP folder (e.g. Sent, Drafts)."""
        client = await self.connect()
        folder = normalize_folder(folder)
        resp = await client.append(raw_message, mailbox=folder, flags=flags)
        if resp.result != "OK":
            raise RuntimeError(f"APPEND to {folder} failed: {resp.lines}")
        return "appended"

    async def append_draft(self, raw_message: bytes, folder: str = "Drafts") -> str:
        await self.append_message(raw_message, folder, flags=r"(\Draft \Seen)")
        return "saved"

    async def health_check(self) -> dict[str, Any]:
        client = await self.connect()
        resp = await client.noop()
        folders = await self.list_folders()
        return {
            "ok": resp.result == "OK",
            "host": self.cfg.imap_host,
            "port": self.cfg.imap_port,
            "folder_count": len(folders),
        }


# Process-wide shared client
_shared: ImapClient | None = None
_lock = asyncio.Lock()


async def get_imap() -> ImapClient:
    global _shared
    async with _lock:
        if _shared is None:
            _shared = ImapClient()
        return _shared
