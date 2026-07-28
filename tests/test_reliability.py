"""Reliability and parsing unit tests."""

from email.message import EmailMessage

from privateemail_mcp.errors import map_mail_error, validate_uid
from privateemail_mcp.mail.imap_client import ImapClient
from privateemail_mcp.mail.parsing import build_message, html_to_text, parse_message_bytes


def test_html_to_text():
    assert "Hello" in html_to_text("<p>Hello <b>world</b></p>")


def test_build_message():
    msg = build_message(
        from_addr="a@b.com",
        to=["c@d.com"],
        subject="Hi",
        text="Body",
        display_name="Ann",
    )
    assert msg["Subject"] == "Hi"
    assert "Ann" in msg["From"]
    assert msg.get_content().strip() == "Body"


def test_parse_message_bytes_header_only():
    msg = EmailMessage()
    msg["From"] = "Sender <sender@example.com>"
    msg["To"] = "Recipient <recipient@example.com>"
    msg["Subject"] = "Header only"
    msg.set_content("This body should not be parsed when include_body=False")

    detail = parse_message_bytes(
        msg.as_bytes(),
        uid="42",
        folder="INBOX",
        include_body=False,
        snippet_text="Preview text",
    )

    assert detail.subject == "Header only"
    assert detail.text_body == "Preview text"
    assert detail.html_body == ""
    assert detail.attachments == []
    assert detail.raw_headers == {}


def test_extract_fetch_sections():
    header = (
        b"From: Sender <sender@example.com>\r\n"
        b"To: Recipient <recipient@example.com>\r\n"
        b"Subject: Hello\r\n"
        b"\r\n"
    )
    snippet = b"Short preview body"
    lines = [
        b'* 1 FETCH (FLAGS (\\Seen) BODY[HEADER] {120}',
        header,
        b' BODY[TEXT]<0.1024> {18}',
        snippet,
        b")",
        b"Fetch completed (0.001 sec).",
    ]

    header_raw, snippet_raw, flags = ImapClient._extract_fetch_sections(lines)

    assert header_raw == header
    assert snippet_raw == snippet
    assert "Seen" in flags


def test_validate_uid_rejects_bad_values():
    try:
        validate_uid("abc")
    except Exception as exc:
        assert "Invalid IMAP UID" in str(exc)
    else:
        raise AssertionError("expected invalid uid to raise")


def test_map_mail_error_select_failed():
    err = map_mail_error(RuntimeError("SELECT Missing failed: NO"), action="list emails")
    assert "Folder not found" in str(err)
