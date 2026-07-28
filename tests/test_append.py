"""Tests for reliable Sent-folder APPEND helpers."""

from privateemail_mcp.errors import map_mail_error
from privateemail_mcp.mail.append import normalize_rfc822_crlf, quote_mailbox


def test_normalize_rfc822_crlf_lf_only():
    raw = b"From: a@b.com\nTo: c@d.com\n\nBody\n"
    out = normalize_rfc822_crlf(raw)
    assert out == b"From: a@b.com\r\nTo: c@d.com\r\n\r\nBody\r\n"
    assert b"\n" not in out.replace(b"\r\n", b"")


def test_normalize_rfc822_crlf_already_crlf():
    raw = b"From: a@b.com\r\nSubject: Hi\r\n\r\nBody\r\n"
    assert normalize_rfc822_crlf(raw) == raw


def test_normalize_rfc822_crlf_mixed():
    raw = b"From: a@b.com\r\nTo: c@d.com\n\nBody"
    out = normalize_rfc822_crlf(raw)
    assert out == b"From: a@b.com\r\nTo: c@d.com\r\n\r\nBody"


def test_quote_mailbox_special_use():
    assert quote_mailbox("Sent") == '"Sent"'
    assert quote_mailbox("Drafts") == '"Drafts"'
    assert quote_mailbox("INBOX") == '"INBOX"'


def test_quote_mailbox_already_quoted():
    assert quote_mailbox('"Sent"') == '"Sent"'


def test_map_sent_archive_error_before_timeout():
    err = map_mail_error(
        RuntimeError(
            "Email was delivered via SMTP (message_id=<x>) but saving a copy to the "
            "Sent folder failed after retries: timed out"
        ),
        action="send email",
    )
    assert "archive it in Sent" in str(err)
    assert "Recipients still received it" in str(err)
