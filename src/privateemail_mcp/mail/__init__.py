"""Mail submodule."""

from .imap_client import ImapClient, imap_session
from .smtp_client import SmtpClient, get_smtp

__all__ = ["ImapClient", "SmtpClient", "imap_session", "get_smtp"]
