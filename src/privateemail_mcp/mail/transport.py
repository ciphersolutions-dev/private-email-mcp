"""TCP/TLS helpers for PrivateEmail IMAP and SMTP.

Supports SSH LocalForward tunnels: connect to 127.0.0.1 while presenting
TLS SNI / hostname checks for mail.privateemail.com.
"""

from __future__ import annotations

import asyncio
import imaplib
import ipaddress
import logging
import socket
import ssl
from typing import TYPE_CHECKING

import aioimaplib
from aioimaplib.aioimaplib import IMAP4ClientProtocol

if TYPE_CHECKING:
    from privateemail_mcp.config import Config

logger = logging.getLogger("privateemail_mcp.transport")

DEFAULT_TLS_HOSTNAME = "mail.privateemail.com"


def is_loopback_host(host: str) -> bool:
    value = (host or "").strip().lower()
    if value in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def resolve_tls_hostname(cfg: "Config", *, for_imap: bool = True) -> str:
    """Hostname used for TLS SNI and certificate verification."""
    if cfg.tls_hostname:
        return cfg.tls_hostname
    host = cfg.imap_host if for_imap else cfg.smtp_host
    if is_loopback_host(host):
        return DEFAULT_TLS_HOSTNAME
    return host


def make_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(ssl.Purpose.SERVER_AUTH)


def tcp_connect(host: str, port: int, timeout: float) -> socket.socket:
    """Blocking TCP connect with an explicit timeout."""
    return socket.create_connection((host, port), timeout=timeout)


class Imap4SSL(aioimaplib.IMAP4_SSL):
    """IMAP4_SSL that can verify certs for a different TLS hostname (tunnels)."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 993,
        loop: asyncio.AbstractEventLoop | None = None,
        timeout: float = 10.0,
        ssl_context: ssl.SSLContext | None = None,
        *,
        tls_hostname: str | None = None,
    ):
        self._tls_hostname = tls_hostname or host
        super().__init__(host=host, port=port, loop=loop, timeout=timeout, ssl_context=ssl_context)

    def create_client(
        self,
        host: str,
        port: int,
        loop: asyncio.AbstractEventLoop,
        conn_lost_cb=None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if ssl_context is None:
            ssl_context = make_ssl_context()
        local_loop = loop if loop is not None else asyncio.get_running_loop()
        self.protocol = IMAP4ClientProtocol(local_loop, conn_lost_cb)
        self._client_task = local_loop.create_task(
            local_loop.create_connection(
                lambda: self.protocol,
                host,
                port,
                ssl=ssl_context,
                server_hostname=self._tls_hostname,
            )
        )


class SyncImap4SSL(imaplib.IMAP4_SSL):
    """imaplib.IMAP4_SSL with explicit TLS server_hostname for tunnels."""

    def __init__(
        self,
        host: str = "",
        port: int = imaplib.IMAP4_SSL_PORT,
        *,
        ssl_context: ssl.SSLContext | None = None,
        timeout: float | None = None,
        tls_hostname: str | None = None,
    ):
        self._tls_hostname = tls_hostname or host
        super().__init__(host=host, port=port, ssl_context=ssl_context, timeout=timeout)

    def _create_socket(self, timeout):  # type: ignore[override]
        sock = socket.create_connection((self.host, self.port), timeout)
        server_hostname = self._tls_hostname or self.host
        return self.ssl_context.wrap_socket(sock, server_hostname=server_hostname)
