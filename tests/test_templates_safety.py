"""Mail parsing unit tests."""

from privateemail_mcp.mail.parsing import build_message, html_to_text


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
