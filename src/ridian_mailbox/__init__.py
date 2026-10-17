"""Ridian's mailbox-scoped HTTP client. Sending/calendars use separate MCP grants."""

from .client import Mailbox, MailboxError

__all__ = ["Mailbox", "MailboxError"]
__version__ = "0.1.0a4"
