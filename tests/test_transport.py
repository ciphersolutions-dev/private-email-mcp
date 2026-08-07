"""Transport and timeout unit tests."""

from privateemail_mcp.config import Config
from privateemail_mcp.errors import map_mail_error
from privateemail_mcp.mail.transport import (
    is_loopback_host,
    resolve_tls_hostname,
)


def _cfg(**overrides) -> Config:
    base = dict(
        address="user@example.com",
        password="secret",
        display_name="",
        imap_host="mail.privateemail.com",
        imap_port=993,
        smtp_host="mail.privateemail.com",
        smtp_port=465,
        max_attachment_bytes=1024,
        connect_timeout=12.0,
        command_timeout=30.0,
        tls_hostname="",
    )
    base.update(overrides)
    return Config(**base)


def test_loopback_detection():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("mail.privateemail.com")


def test_tls_hostname_defaults_for_tunnel():
    cfg = _cfg(imap_host="127.0.0.1", imap_port=21993)
    assert resolve_tls_hostname(cfg) == "mail.privateemail.com"


def test_tls_hostname_explicit():
    cfg = _cfg(imap_host="127.0.0.1", tls_hostname="mail.privateemail.com")
    assert resolve_tls_hostname(cfg) == "mail.privateemail.com"


def test_direct_timeout_mentions_tunnel(monkeypatch):
    monkeypatch.setenv("PRIVATEEMAIL_ADDRESS", "user@example.com")
    monkeypatch.setenv("PRIVATEEMAIL_PASSWORD", "secret")
    monkeypatch.setenv("PRIVATEEMAIL_IMAP_HOST", "mail.privateemail.com")
    err = map_mail_error(TimeoutError("timed out"), action="list folders")
    text = str(err)
    assert "could not connect" in text
    assert "mail-tunnel.sh" in text


def test_tunnel_timeout_mentions_restart(monkeypatch):
    monkeypatch.setenv("PRIVATEEMAIL_ADDRESS", "user@example.com")
    monkeypatch.setenv("PRIVATEEMAIL_PASSWORD", "secret")
    monkeypatch.setenv("PRIVATEEMAIL_IMAP_HOST", "127.0.0.1")
    err = map_mail_error(TimeoutError("timed out"), action="list folders")
    text = str(err)
    assert "tunnel" in text.lower()
    assert "mail-tunnel.sh" in text
