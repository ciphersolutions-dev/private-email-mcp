"""SMTP client for PrivateEmail."""

from __future__ import annotations

import logging
import uuid
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from email.utils import format_datetime, getaddresses
from typing import Any

import aiosmtplib

from privateemail_mcp.config import Config, get_config
from privateemail_mcp.mail.append import append_with_retries, normalize_rfc822_crlf
from privateemail_mcp.mail.parsing import build_message

logger = logging.getLogger("privateemail_mcp.smtp")


class SmtpClient:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or get_config()

    def _ensure_message_id(self, msg: EmailMessage) -> str:
        mid = msg.get("Message-ID")
        if mid:
            return mid
        domain = self.cfg.address.split("@")[-1] if "@" in self.cfg.address else "localhost"
        mid = f"<{uuid.uuid4()}@{domain}>"
        msg["Message-ID"] = mid
        return mid

    def _ensure_date(self, msg: EmailMessage) -> None:
        if not msg.get("Date"):
            from datetime import datetime, timezone

            msg["Date"] = format_datetime(datetime.now(timezone.utc))

    def _archive_bytes(self, msg: EmailMessage) -> bytes:
        """Snapshot message bytes with CRLF endings for IMAP APPEND."""
        try:
            raw = msg.as_bytes(policy=SMTP_POLICY)
        except TypeError:
            # Older EmailMessage.as_bytes may not accept policy kwarg.
            raw = msg.as_bytes()
        return normalize_rfc822_crlf(raw)

    async def _save_to_sent_bytes(self, raw: bytes) -> dict[str, Any]:
        """IMAP APPEND into Sent — required after every successful SMTP send."""
        result = await append_with_retries(
            self.cfg,
            raw,
            "Sent",
            flags=r"(\Seen)",
            attempts=3,
            backoff_seconds=1.0,
        )
        return {
            "saved_to_sent": True,
            "sent_mailbox": "Sent",
            "sent_append_attempts": result["attempts"],
        }

    async def send_message(
        self,
        msg: EmailMessage,
        *,
        save_to_sent: bool = True,
    ) -> dict[str, Any]:
        mid = self._ensure_message_id(msg)
        self._ensure_date(msg)

        recipients: list[str] = []
        for header in ("To", "Cc", "Bcc"):
            if msg.get(header):
                for _, addr in getaddresses([msg.get(header) or ""]):
                    if addr:
                        recipients.append(addr)

        # Snapshot for Sent (keeps Bcc) before stripping Bcc for SMTP
        archive_bytes = self._archive_bytes(msg)

        if "Bcc" in msg:
            del msg["Bcc"]

        use_tls = self.cfg.smtp_port == 465
        await aiosmtplib.send(
            msg,
            hostname=self.cfg.smtp_host,
            port=self.cfg.smtp_port,
            username=self.cfg.address,
            password=self.cfg.password,
            start_tls=not use_tls,
            use_tls=use_tls,
        )

        result: dict[str, Any] = {
            "ok": True,
            "message_id": mid,
            "recipients": recipients,
            "subject": msg.get("Subject"),
            "smtp_delivered": True,
        }
        if save_to_sent:
            try:
                result.update(await self._save_to_sent_bytes(archive_bytes))
            except Exception as exc:
                # Delivery already happened — surface a hard failure so agents
                # do not silently treat Sent archival as optional.
                logger.error("SMTP delivered but Sent APPEND failed: %s", exc)
                raise RuntimeError(
                    f"Email was delivered via SMTP (message_id={mid}) but saving "
                    f"a copy to the Sent folder failed after retries: {exc}. "
                    "Do not assume the message is missing from recipients — "
                    "retry save via IMAP APPEND, or re-check Sent after reconnect."
                ) from exc
        return result

    async def send_email(
        self,
        *,
        to: list[str] | str,
        subject: str,
        text: str | None = None,
        html: str | None = None,
        cc: list[str] | str | None = None,
        bcc: list[str] | str | None = None,
        reply_to: str | None = None,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        save_to_sent: bool = True,
    ) -> dict[str, Any]:
        def as_list(v: list[str] | str | None) -> list[str]:
            if v is None:
                return []
            if isinstance(v, str):
                return [x.strip() for x in v.split(",") if x.strip()]
            return list(v)

        msg = build_message(
            from_addr=self.cfg.address,
            to=as_list(to),
            subject=subject,
            text=text,
            html=html,
            cc=as_list(cc),
            bcc=as_list(bcc),
            reply_to=reply_to,
            in_reply_to=in_reply_to,
            references=references,
            display_name=self.cfg.display_name or None,
            attachments=attachments,
        )
        return await self.send_message(msg, save_to_sent=save_to_sent)

    async def health_check(self) -> dict[str, Any]:
        use_tls = self.cfg.smtp_port == 465
        smtp = aiosmtplib.SMTP(
            hostname=self.cfg.smtp_host,
            port=self.cfg.smtp_port,
            use_tls=use_tls,
            start_tls=not use_tls,
        )
        await smtp.connect()
        try:
            await smtp.login(self.cfg.address, self.cfg.password)
            return {"ok": True, "host": self.cfg.smtp_host, "port": self.cfg.smtp_port}
        finally:
            try:
                await smtp.quit()
            except Exception:
                pass


_shared: SmtpClient | None = None


def get_smtp() -> SmtpClient:
    global _shared
    if _shared is None:
        _shared = SmtpClient()
    return _shared
