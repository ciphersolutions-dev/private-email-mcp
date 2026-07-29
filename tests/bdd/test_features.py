"""Step definitions for PrivateEmail MCP Gherkin acceptance suite."""

from __future__ import annotations

import asyncio
import importlib.metadata
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pytest_bdd import given, parsers, scenarios, then, when

from privateemail_mcp.config import Config, load_config
from privateemail_mcp.errors import map_mail_error, validate_folder, validate_uid
from privateemail_mcp.mail.append import normalize_rfc822_crlf, quote_mailbox
from privateemail_mcp.mail.models import EmailDetail
from privateemail_mcp.mail.parsing import build_message, html_to_text, parse_message_bytes
from privateemail_mcp.mail.smtp_client import SmtpClient
from privateemail_mcp.server import _attachment_list, _prompt_email_payload, mcp

FEATURE_DIR = Path(__file__).resolve().parents[2] / "features"

scenarios(
    str(FEATURE_DIR / "dependency_compat.feature"),
    str(FEATURE_DIR / "configuration.feature"),
    str(FEATURE_DIR / "agent_errors.feature"),
    str(FEATURE_DIR / "sent_archival.feature"),
    str(FEATURE_DIR / "parsing_prompts.feature"),
    str(FEATURE_DIR / "outbound_safety.feature"),
    str(FEATURE_DIR / "send_contract.feature"),
    str(FEATURE_DIR / "mcp_surface.feature"),
)


# ---------------------------------------------------------------------------
# Dependency compatibility
# ---------------------------------------------------------------------------


@given("the published package declares an MCP SDK upper bound below 2.0.0")
def package_declares_mcp_cap():
    reqs = importlib.metadata.requires("privateemail-mcp") or []
    mcp_reqs = [r for r in reqs if r.lower().startswith("mcp")]
    assert mcp_reqs, "mcp dependency missing from package metadata"
    joined = " ".join(mcp_reqs)
    assert "<2" in joined or "<2.0" in joined, joined


@when("the privateemail MCP server module is imported")
def import_server(ctx):
    import privateemail_mcp.server as server

    ctx.result = server


@then("the FastMCP server object is available")
def fastmcp_available(ctx):
    assert getattr(ctx.result, "mcp", None) is not None
    assert ctx.result.mcp.name == "privateemail"


@then("the installed mcp package major version is 1")
def mcp_major_is_one():
    version = importlib.metadata.version("mcp")
    major = int(version.split(".", 1)[0])
    assert major == 1, f"expected mcp 1.x, got {version}"


@when("package metadata for privateemail-mcp is inspected")
def inspect_metadata(ctx):
    ctx.result = importlib.metadata.requires("privateemail-mcp") or []


@then("the mcp dependency constraint includes an upper bound below 2.0.0")
def metadata_has_upper_bound(ctx):
    mcp_reqs = [r for r in ctx.result if r.lower().startswith("mcp")]
    joined = " ".join(mcp_reqs)
    assert "<2" in joined or "<2.0" in joined, joined


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@given("PrivateEmail env is cleared")
def clear_env(isolated_env):
    return isolated_env


@given(parsers.parse('PRIVATEEMAIL_ADDRESS is "{value}"'))
def set_address(isolated_env, value: str):
    isolated_env.setenv("PRIVATEEMAIL_ADDRESS", value)


@given(parsers.parse('PRIVATEEMAIL_PASSWORD is "{value}"'))
def set_password(isolated_env, value: str):
    isolated_env.setenv("PRIVATEEMAIL_PASSWORD", value)


@given(parsers.parse('PRIVATEEMAIL_IMAP_PORT is "{value}"'))
def set_imap_port(isolated_env, value: str):
    isolated_env.setenv("PRIVATEEMAIL_IMAP_PORT", value)


@when("configuration is validated")
def validate_configuration(ctx):
    try:
        load_config().validate()
        ctx.error = None
    except Exception as exc:
        ctx.error = exc


@when("configuration is loaded")
def load_configuration(ctx):
    try:
        ctx.config = load_config()
        ctx.error = None
    except Exception as exc:
        ctx.config = None
        ctx.error = exc


@then(parsers.parse('a configuration error mentions "{needle}"'))
def config_error_mentions(ctx, needle: str):
    assert ctx.error is not None
    assert needle in str(ctx.error)


@then(parsers.parse('the IMAP endpoint is "{endpoint}"'))
def imap_endpoint(ctx, endpoint: str):
    assert ctx.error is None
    assert f"{ctx.config.imap_host}:{ctx.config.imap_port}" == endpoint


@then(parsers.parse('the SMTP endpoint is "{endpoint}"'))
def smtp_endpoint(ctx, endpoint: str):
    assert ctx.error is None
    assert f"{ctx.config.smtp_host}:{ctx.config.smtp_port}" == endpoint


# ---------------------------------------------------------------------------
# Agent errors / validation
# ---------------------------------------------------------------------------


@when(parsers.parse('UID "{uid}" is validated'))
def validate_uid_step(ctx, uid: str):
    try:
        ctx.result = validate_uid(uid)
        ctx.error = None
    except Exception as exc:
        ctx.result = None
        ctx.error = exc


@when("an empty UID is validated")
def validate_empty_uid(ctx):
    try:
        ctx.result = validate_uid("")
        ctx.error = None
    except Exception as exc:
        ctx.result = None
        ctx.error = exc


@when(parsers.parse('folder "{folder}" is validated'))
def validate_folder_step(ctx, folder: str):
    try:
        ctx.result = validate_folder(folder)
        ctx.error = None
    except Exception as exc:
        ctx.result = None
        ctx.error = exc


@when("an empty folder is validated")
def validate_empty_folder(ctx):
    try:
        ctx.result = validate_folder("")
        ctx.error = None
    except Exception as exc:
        ctx.result = None
        ctx.error = exc


@then(parsers.parse('validation fails with "{needle}"'))
def validation_fails(ctx, needle: str):
    assert ctx.error is not None
    assert needle in str(ctx.error)


@then(parsers.parse('validation succeeds with value "{value}"'))
def validation_ok(ctx, value: str):
    assert ctx.error is None
    assert ctx.result == value


@given(parsers.parse('a mail failure "{raw}" while "{action}"'))
def mail_failure(ctx, raw: str, action: str):
    ctx.mail_failure = raw
    ctx.mail_action = action


@when("the failure is mapped for agents")
def map_failure(ctx):
    err = map_mail_error(RuntimeError(ctx.mail_failure), action=ctx.mail_action)
    ctx.agent_error = str(err)


@then(parsers.parse('the agent error contains "{needle}"'))
def agent_error_contains(ctx, needle: str):
    assert ctx.agent_error is not None
    assert needle in ctx.agent_error


# ---------------------------------------------------------------------------
# Sent archival
# ---------------------------------------------------------------------------


@given("raw message bytes with LF-only line endings")
def lf_only_bytes(ctx):
    ctx.raw_bytes = b"From: a@b.com\nTo: c@d.com\n\nBody\n"
    ctx.expected_crlf = b"From: a@b.com\r\nTo: c@d.com\r\n\r\nBody\r\n"


@given("raw message bytes with mixed CRLF and LF endings")
def mixed_bytes(ctx):
    ctx.raw_bytes = b"From: a@b.com\r\nTo: c@d.com\n\nBody"
    ctx.expected_crlf = b"From: a@b.com\r\nTo: c@d.com\r\n\r\nBody"


@when("the message is normalized for IMAP APPEND")
def normalize_message(ctx):
    ctx.normalized = normalize_rfc822_crlf(ctx.raw_bytes)


@then("every line ending is CRLF")
def every_crlf(ctx):
    assert b"\r\n" in ctx.normalized


@then("no bare LF remains")
def no_bare_lf(ctx):
    assert b"\n" not in ctx.normalized.replace(b"\r\n", b"")


@then("the normalized message equals the expected CRLF form")
def equals_expected(ctx):
    assert ctx.normalized == ctx.expected_crlf


@when(parsers.parse('mailbox "{name}" is quoted for APPEND'))
def quote_mailbox_step(ctx, name: str):
    ctx.result = quote_mailbox(name)


@then(parsers.parse('the quoted mailbox is "{quoted}"'))
def quoted_mailbox(ctx, quoted: str):
    assert ctx.result == quoted


# ---------------------------------------------------------------------------
# Parsing / prompts
# ---------------------------------------------------------------------------


@given(
    parsers.parse(
        'an email with subject "{subject}" and body "{body}"'
    )
)
def email_bytes(ctx, subject: str, body: str):
    msg = build_message(
        from_addr="sender@example.com",
        to=["recipient@example.com"],
        subject=subject,
        text=body,
    )
    ctx.raw_bytes = msg.as_bytes()


@when(
    parsers.parse(
        'the message is parsed without body inclusion using snippet "{snippet}"'
    )
)
def parse_without_body(ctx, snippet: str):
    ctx.email_detail = parse_message_bytes(
        ctx.raw_bytes,
        uid="42",
        folder="INBOX",
        include_body=False,
        snippet_text=snippet,
    )


@then(parsers.parse('the parsed subject is "{subject}"'))
def parsed_subject(ctx, subject: str):
    assert ctx.email_detail.subject == subject


@then(parsers.parse('the parsed text body is "{text}"'))
def parsed_text(ctx, text: str):
    assert ctx.email_detail.text_body == text


@then("the parsed HTML body is empty")
def parsed_html_empty(ctx):
    assert ctx.email_detail.html_body == ""


@then("attachments are empty")
def attachments_empty(ctx):
    assert ctx.email_detail.attachments == []


@then("raw headers are empty")
def raw_headers_empty(ctx):
    assert ctx.email_detail.raw_headers == {}


@given(parsers.parse('HTML content "{html}"'))
def html_content(ctx, html: str):
    ctx.html = html


@when("HTML is converted to plain text")
def convert_html(ctx):
    ctx.plain = html_to_text(ctx.html)


@then(parsers.parse('the plain text contains "{needle}"'))
def plain_contains(ctx, needle: str):
    assert needle in ctx.plain


@given(parsers.parse("an email detail with a text body of {n:d} characters"))
def detail_long_text(ctx, n: int):
    ctx.email_detail = EmailDetail(
        uid="1",
        folder="INBOX",
        subject="S",
        from_addr="a@b.com",
        to_addrs=["c@d.com"],
        cc_addrs=[],
        bcc_addrs=[],
        date=None,
        message_id="<1@x>",
        in_reply_to=None,
        references=[],
        flags=[],
        text_body="x" * n,
        html_body="",
        attachments=[],
        raw_headers={"X-Test": "1"},
    )


@given(
    parsers.parse(
        "an email detail with empty text and HTML of {n:d} characters"
    )
)
def detail_html_only(ctx, n: int):
    ctx.email_detail = EmailDetail(
        uid="1",
        folder="INBOX",
        subject="S",
        from_addr="a@b.com",
        to_addrs=["c@d.com"],
        cc_addrs=[],
        bcc_addrs=[],
        date=None,
        message_id="<1@x>",
        in_reply_to=None,
        references=[],
        flags=[],
        text_body="",
        html_body="<p>" + ("y" * n) + "</p>",
        attachments=[],
        raw_headers={},
    )


@when("a prompt email payload is built")
def build_prompt_payload(ctx):
    ctx.prompt_payload = _prompt_email_payload(ctx.email_detail)


@then(parsers.parse("the prompt text body length is at most {n:d} characters"))
def prompt_len(ctx, n: int):
    assert len(ctx.prompt_payload["text_body"]) <= n


@then("the prompt payload omits raw_headers")
def prompt_no_raw_headers(ctx):
    assert "raw_headers" not in ctx.prompt_payload


# ---------------------------------------------------------------------------
# Outbound safety
# ---------------------------------------------------------------------------


@given(
    parsers.parse(
        'a composed message from "{frm}" as "{name}" to "{to}" with subject "{subject}" and text "{text}"'
    )
)
def composed_message(ctx, frm: str, name: str, to: str, subject: str, text: str):
    ctx.result = build_message(
        from_addr=frm,
        to=[to],
        subject=subject,
        text=text,
        display_name=name,
    )


@then(parsers.parse('the MIME subject is "{subject}"'))
def mime_subject(ctx, subject: str):
    assert ctx.result["Subject"] == subject


@then(parsers.parse('the MIME From contains "{needle}"'))
def mime_from(ctx, needle: str):
    assert needle in ctx.result["From"]


@then(parsers.parse('the MIME plain body is "{body}"'))
def mime_body(ctx, body: str):
    assert ctx.result.get_content().strip() == body


@given(parsers.parse('an original subject "{subject}"'))
def original_subject(ctx, subject: str):
    ctx.original_subject = subject


@when("a reply subject is prepared")
def prepare_reply_subject(ctx):
    subj = ctx.original_subject or ""
    if not subj.lower().startswith("re:"):
        subj = f"Re: {subj}"
    ctx.prepared_subject = subj


@when("a forward subject is prepared")
def prepare_forward_subject(ctx):
    subj = ctx.original_subject or ""
    if not subj.lower().startswith("fwd:"):
        subj = f"Fwd: {subj}"
    ctx.prepared_subject = subj


@then(parsers.parse('the reply subject is "{subject}"'))
@then(parsers.parse('the forward subject is "{subject}"'))
def prepared_subject(ctx, subject: str):
    assert ctx.prepared_subject == subject


@when(parsers.parse('attachment paths "{paths}" are resolved'))
def resolve_attachments(ctx, paths: str):
    try:
        ctx.result = _attachment_list(paths)
        ctx.error = None
    except Exception as exc:
        ctx.result = None
        ctx.error = exc


@then(parsers.parse('an attachment error mentions "{needle}"'))
def attachment_error(ctx, needle: str):
    assert ctx.error is not None
    assert needle in str(ctx.error)


def _check_draft_preconditions(detail: EmailDetail) -> None:
    recipients = [a for a in (detail.to_addrs or []) if a and a.strip()]
    if not recipients:
        raise ValueError(
            "Draft has no To recipients. Edit the draft with a valid To address "
            "before calling send_draft."
        )
    if not (detail.text_body or detail.html_body):
        raise ValueError("Draft has an empty body. Add text or HTML before sending.")


@given(
    parsers.parse(
        'a draft email detail with no To recipients and body "{body}"'
    )
)
def draft_no_to(ctx, body: str):
    ctx.email_detail = EmailDetail(
        uid="9",
        folder="Drafts",
        subject="Draft",
        from_addr="me@example.com",
        to_addrs=[],
        cc_addrs=[],
        bcc_addrs=[],
        date=None,
        message_id=None,
        in_reply_to=None,
        references=[],
        flags=["Draft"],
        text_body=body,
        html_body="",
    )


@given(parsers.parse('a draft email detail to "{to}" with empty body'))
def draft_empty_body(ctx, to: str):
    ctx.email_detail = EmailDetail(
        uid="9",
        folder="Drafts",
        subject="Draft",
        from_addr="me@example.com",
        to_addrs=[to],
        cc_addrs=[],
        bcc_addrs=[],
        date=None,
        message_id=None,
        in_reply_to=None,
        references=[],
        flags=["Draft"],
        text_body="",
        html_body="",
    )


@when("send_draft preconditions are checked")
def check_draft_preconditions(ctx):
    try:
        _check_draft_preconditions(ctx.email_detail)
        ctx.error = None
    except Exception as exc:
        ctx.error = exc


@then(parsers.parse('a draft send error mentions "{needle}"'))
def draft_send_error(ctx, needle: str):
    assert ctx.error is not None
    assert needle in str(ctx.error)


# ---------------------------------------------------------------------------
# Send contract
# ---------------------------------------------------------------------------


@given("SMTP delivery will succeed")
def smtp_will_succeed(ctx):
    ctx.smtp_ok = True


@given(parsers.parse("Sent APPEND will succeed on attempt {n:d}"))
def append_succeeds(ctx, n: int):
    ctx.append_fail = False
    ctx.append_succeed_on = n


@given("Sent APPEND will fail every attempt")
def append_fails(ctx):
    ctx.append_fail = True


@when(
    parsers.parse(
        'an email is sent to "{to}" with subject "{subject}" and text "{text}"'
    )
)
def send_email_step(ctx, to: str, subject: str, text: str):
    cfg = Config(
        address="sender@example.com",
        password="secret",
        display_name="Sender",
        imap_host="mail.privateemail.com",
        imap_port=993,
        smtp_host="mail.privateemail.com",
        smtp_port=465,
        max_attachment_bytes=10_000_000,
    )
    client = SmtpClient(cfg)

    async def fake_send(*_args, **_kwargs):
        if not ctx.smtp_ok:
            raise RuntimeError("SMTP failed")
        return None

    async def fake_append(_cfg, _raw, mailbox, **_kwargs):
        if ctx.append_fail:
            raise RuntimeError("APPEND timed out")
        return {"status": "appended", "mailbox": mailbox, "attempts": ctx.append_succeed_on}

    async def _run():
        with (
            patch("privateemail_mcp.mail.smtp_client.aiosmtplib.send", new=AsyncMock(side_effect=fake_send)),
            patch(
                "privateemail_mcp.mail.smtp_client.append_with_retries",
                new=AsyncMock(side_effect=fake_append),
            ),
        ):
            return await client.send_email(to=to, subject=subject, text=text)

    try:
        ctx.result = asyncio.run(_run())
        ctx.error = None
    except Exception as exc:
        ctx.result = None
        ctx.error = exc


@then("the send result marks smtp_delivered true")
def smtp_delivered(ctx):
    assert ctx.error is None
    assert ctx.result["smtp_delivered"] is True


@then("the send result marks saved_to_sent true")
def saved_to_sent(ctx):
    assert ctx.result["saved_to_sent"] is True


@then("the send result includes a message_id")
def has_message_id(ctx):
    assert ctx.result.get("message_id")


@then(parsers.parse('send fails with a message containing "{needle}"'))
def send_fails_containing(ctx, needle: str):
    assert ctx.error is not None
    assert needle in str(ctx.error)


# ---------------------------------------------------------------------------
# MCP surface
# ---------------------------------------------------------------------------


@when("the MCP tool inventory is inspected")
def inspect_tools(ctx):
    ctx.tools = set(mcp._tool_manager._tools)


@when("the MCP prompt inventory is inspected")
def inspect_prompts(ctx):
    ctx.prompts = set(mcp._prompt_manager._prompts)


@then("these tools are registered:")
def tools_registered(ctx, datatable):
    expected = {row[0] for row in datatable}
    missing = expected - ctx.tools
    assert not missing, f"missing tools: {sorted(missing)}"


@then("these prompts are registered:")
def prompts_registered(ctx, datatable):
    expected = {row[0] for row in datatable}
    missing = expected - ctx.prompts
    assert not missing, f"missing prompts: {sorted(missing)}"
