"""Mail submodule."""

from .imap_client import ImapClient, get_imap
from .smtp_client import SmtpClient, get_smtp

__all__ = ["ImapClient", "SmtpClient", "get_imap", "get_smtp"]
