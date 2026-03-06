"""Email tool for reading (IMAP) and sending (SMTP) emails."""

import base64
import json
import re
import smtplib
from datetime import date, datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from imap_tools import AND, MailBox, MailMessage

from src.email_store import EmailAccountStore
from src.tools.base import Tool

# Maximum characters of body text returned in list views.
_PREVIEW_LENGTH = 500
# Maximum characters of body text returned for a single email.
_FULL_BODY_LENGTH = 50_000


class _HTMLTextExtractor(HTMLParser):
    """Extract visible text from HTML, skipping script/style content."""

    _SKIP_TAGS = frozenset({"script", "style", "head"})

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._parts)).strip()


def _strip_html(html: str) -> str:
    """Convert HTML to plain text, stripping tags and script/style content."""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        # Fallback for severely malformed HTML
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()


def _body_text(msg: MailMessage, max_len: int = _PREVIEW_LENGTH) -> str:
    """Extract body text from a message, preferring plaintext over HTML."""
    text = msg.text
    if not text and msg.html:
        text = _strip_html(msg.html)
    if text and len(text) > max_len:
        text = text[:max_len] + "…"
    return text or ""


def _msg_to_dict(msg: MailMessage, full_body: bool = False) -> dict[str, Any]:
    """Convert a MailMessage to a JSON-friendly dict."""
    max_len = _FULL_BODY_LENGTH if full_body else _PREVIEW_LENGTH
    result: dict[str, Any] = {
        "uid": msg.uid,
        "from": msg.from_,
        "to": list(msg.to),
        "cc": list(msg.cc) if msg.cc else [],
        "subject": msg.subject,
        "date": msg.date.isoformat() if msg.date else None,
        "seen": msg.flags and "\\Seen" in msg.flags,
        "body": _body_text(msg, max_len),
    }
    if msg.attachments:
        result["attachments"] = [
            {"filename": att.filename, "size": att.size}
            for att in msg.attachments
        ]
    return result


class EmailTool(Tool):
    """Tool that gives the LLM access to email via IMAP/SMTP.

    Supports managing accounts, reading/searching emails, sending,
    and basic operations (mark read, move, delete). Works with any
    IMAP/SMTP provider (Gmail, Outlook, generic).
    """

    def __init__(self, store: EmailAccountStore) -> None:
        self._store = store

    @property
    def name(self) -> str:
        return "email"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Manage email accounts and read/send emails via IMAP/SMTP. "
                    "First add an account, then read, search, or send emails. "
                    "Supports Gmail, Outlook, and any IMAP/SMTP provider."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "add_account", "list_accounts", "remove_account",
                                "list_folders", "read_emails", "search_emails",
                                "read_email", "send_email",
                                "mark_read", "move_email", "delete_email",
                                "list_attachments", "download_attachment", "upload_attachment",
                            ],
                            "description": (
                                "'add_account' to register an email account, "
                                "'list_accounts' to show all, "
                                "'remove_account' to unregister, "
                                "'list_folders' to list mailbox folders, "
                                "'read_emails' to fetch recent emails, "
                                "'search_emails' to search by criteria, "
                                "'read_email' to read a single email in full, "
                                "'send_email' to send an email, "
                                "'mark_read' to mark as read, "
                                "'move_email' to move to folder, "
                                "'delete_email' to delete, "
                                "'list_attachments' to list attachments for an email, "
                                "'download_attachment' to save attachment to file, "
                                "'upload_attachment' to send email with attachment."
                            ),
                        },
                        "account": {
                            "type": "string",
                            "description": "Account name (for email operations).",
                        },
                        "name": {
                            "type": "string",
                            "description": "Account name (for add/remove).",
                        },
                        "email_address": {
                            "type": "string",
                            "description": "Full email address (for add_account).",
                        },
                        "password": {
                            "type": "string",
                            "description": "Password or app-specific password.",
                        },
                        "imap_host": {
                            "type": "string",
                            "description": "IMAP server host (e.g. 'imap.gmail.com').",
                        },
                        "smtp_host": {
                            "type": "string",
                            "description": "SMTP server host (e.g. 'smtp.gmail.com').",
                        },
                        "imap_port": {
                            "type": "integer",
                            "description": "IMAP port (default: 993).",
                        },
                        "smtp_port": {
                            "type": "integer",
                            "description": "SMTP port (default: 587).",
                        },
                        "provider": {
                            "type": "string",
                            "enum": ["gmail", "outlook", "generic"],
                            "description": "Provider type hint.",
                        },
                        "folder": {
                            "type": "string",
                            "description": "Mailbox folder (default: 'INBOX').",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max emails to return (default: 10).",
                        },
                        "unread_only": {
                            "type": "boolean",
                            "description": "Only fetch unread emails.",
                        },
                        "uid": {
                            "type": "string",
                            "description": "Email UID (for read_email/mark_read/move/delete).",
                        },
                        "to": {
                            "type": "string",
                            "description": "Recipient email address (for send_email).",
                        },
                        "cc": {
                            "type": "string",
                            "description": "CC recipient (for send_email).",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject (for send/search).",
                        },
                        "body": {
                            "type": "string",
                            "description": "Email body text (for send_email).",
                        },
                        "html": {
                            "type": "boolean",
                            "description": "Send body as HTML (default: false).",
                        },
                        "from_": {
                            "type": "string",
                            "description": "Search: sender address.",
                        },
                        "text": {
                            "type": "string",
                            "description": "Search: text in body.",
                        },
                        "seen": {
                            "type": "boolean",
                            "description": "Search: read/unread filter.",
                        },
                        "date_from": {
                            "type": "string",
                            "description": "Search: emails since date (YYYY-MM-DD).",
                        },
                        "date_to": {
                            "type": "string",
                            "description": "Search: emails until date (YYYY-MM-DD).",
                        },
                        "attachment_index": {
                            "type": "integer",
                            "description": "Attachment index (for download_attachment).",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Path to save attachment (for download_attachment).",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Path to attachment file (for upload_attachment).",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        try:
            if action == "add_account":
                return self._add_account(kwargs)
            elif action == "list_accounts":
                return self._list_accounts()
            elif action == "remove_account":
                return self._remove_account(kwargs)
            elif action == "list_folders":
                return self._list_folders(kwargs)
            elif action == "read_emails":
                return self._read_emails(kwargs)
            elif action == "search_emails":
                return self._search_emails(kwargs)
            elif action == "read_email":
                return self._read_email(kwargs)
            elif action == "send_email":
                return self._send_email(kwargs)
            elif action == "mark_read":
                return self._mark_read(kwargs)
            elif action == "move_email":
                return self._move_email(kwargs)
            elif action == "delete_email":
                return self._delete_email(kwargs)
            elif action == "list_attachments":
                return self._list_attachments(kwargs)
            elif action == "download_attachment":
                return self._download_attachment(kwargs)
            elif action == "upload_attachment":
                return self._upload_attachment(kwargs)
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def _add_account(self, kw: dict) -> str:
        name = kw.get("name")
        email_address = kw.get("email_address")
        password = kw.get("password")
        imap_host = kw.get("imap_host")
        smtp_host = kw.get("smtp_host")

        if not all([name, email_address, password, imap_host, smtp_host]):
            return json.dumps({
                "error": "name, email_address, password, imap_host, and smtp_host are required"
            })

        acct_id = self._store.add(
            name=name,
            email_address=email_address,
            password=password,
            imap_host=imap_host,
            smtp_host=smtp_host,
            imap_port=kw.get("imap_port", 993),
            smtp_port=kw.get("smtp_port", 587),
            provider=kw.get("provider", "generic"),
        )
        return json.dumps({
            "added": True,
            "account_id": acct_id,
            "total_accounts": self._store.count(),
        })

    def _list_accounts(self) -> str:
        accts = self._store.list_all()
        return json.dumps({"accounts": accts, "count": len(accts)}, ensure_ascii=False)

    def _remove_account(self, kw: dict) -> str:
        name = kw.get("name")
        if not name:
            return json.dumps({"error": "name is required for 'remove_account'"})
        removed = self._store.remove(name)
        return json.dumps({"removed": removed, "name": name})

    # ------------------------------------------------------------------
    # IMAP helpers
    # ------------------------------------------------------------------

    def _get_account(self, account_name: str) -> dict[str, Any]:
        """Retrieve account details or raise."""
        acct = self._store.get(account_name)
        if acct is None:
            raise ValueError(f"Account '{account_name}' not found")
        return acct

    def _connect_imap(self, acct: dict[str, Any]) -> MailBox:
        """Create and login to an IMAP mailbox."""
        mailbox = MailBox(acct["imap_host"], acct["imap_port"])
        mailbox.login(acct["email_address"], acct["password"])
        return mailbox

    # ------------------------------------------------------------------
    # IMAP read operations
    # ------------------------------------------------------------------

    def _list_folders(self, kw: dict) -> str:
        account = kw.get("account")
        if not account:
            return json.dumps({"error": "account is required for 'list_folders'"})

        acct = self._get_account(account)
        with self._connect_imap(acct) as mailbox:
            folders = mailbox.folder.list()
            result = [{"name": f.name, "flags": list(f.flags)} for f in folders]
        return json.dumps({"folders": result, "count": len(result)}, ensure_ascii=False)

    def _read_emails(self, kw: dict) -> str:
        account = kw.get("account")
        if not account:
            return json.dumps({"error": "account is required for 'read_emails'"})

        acct = self._get_account(account)
        folder = kw.get("folder", "INBOX")
        limit = kw.get("limit", 10)
        unread_only = kw.get("unread_only", False)

        criteria = AND(seen=False) if unread_only else "ALL"

        with self._connect_imap(acct) as mailbox:
            mailbox.folder.set(folder)
            messages = []
            for msg in mailbox.fetch(criteria, limit=limit, reverse=True):
                messages.append(_msg_to_dict(msg))

        return json.dumps({"emails": messages, "count": len(messages)}, ensure_ascii=False)

    def _search_emails(self, kw: dict) -> str:
        account = kw.get("account")
        if not account:
            return json.dumps({"error": "account is required for 'search_emails'"})

        acct = self._get_account(account)
        folder = kw.get("folder", "INBOX")
        limit = kw.get("limit", 20)

        # Build search criteria
        criteria_kw: dict[str, Any] = {}
        if kw.get("from_"):
            criteria_kw["from_"] = kw["from_"]
        if kw.get("to"):
            criteria_kw["to"] = kw["to"]
        if kw.get("subject"):
            criteria_kw["subject"] = kw["subject"]
        if kw.get("text"):
            criteria_kw["text"] = kw["text"]
        if "seen" in kw and isinstance(kw["seen"], bool):
            criteria_kw["seen"] = kw["seen"]
        if kw.get("date_from"):
            criteria_kw["date_gte"] = date.fromisoformat(kw["date_from"])
        if kw.get("date_to"):
            criteria_kw["date_lt"] = date.fromisoformat(kw["date_to"])

        criteria = AND(**criteria_kw) if criteria_kw else "ALL"

        with self._connect_imap(acct) as mailbox:
            mailbox.folder.set(folder)
            messages = []
            for msg in mailbox.fetch(criteria, limit=limit, reverse=True):
                messages.append(_msg_to_dict(msg))

        return json.dumps({"emails": messages, "count": len(messages)}, ensure_ascii=False)

    def _read_email(self, kw: dict) -> str:
        account = kw.get("account")
        uid = kw.get("uid")
        if not all([account, uid]):
            return json.dumps({"error": "account and uid are required for 'read_email'"})

        acct = self._get_account(account)
        folder = kw.get("folder", "INBOX")

        with self._connect_imap(acct) as mailbox:
            mailbox.folder.set(folder)
            for msg in mailbox.fetch(AND(uid=uid)):
                return json.dumps({"email": _msg_to_dict(msg, full_body=True)}, ensure_ascii=False)

        return json.dumps({"error": f"Email with UID '{uid}' not found"})

    # ------------------------------------------------------------------
    # SMTP send
    # ------------------------------------------------------------------

    def _send_email(self, kw: dict) -> str:
        account = kw.get("account")
        to = kw.get("to")
        subject = kw.get("subject")
        body = kw.get("body")

        if not all([account, to, subject, body]):
            return json.dumps({
                "error": "account, to, subject, and body are required for 'send_email'"
            })

        acct = self._get_account(account)
        is_html = kw.get("html", False)
        cc = kw.get("cc")

        if is_html:
            mime_msg = MIMEMultipart("alternative")
            mime_msg.attach(MIMEText(body, "html"))
        else:
            mime_msg = MIMEText(body, "plain")

        mime_msg["Subject"] = subject
        mime_msg["From"] = acct["email_address"]
        mime_msg["To"] = to
        if cc:
            mime_msg["Cc"] = cc

        smtp_port = acct["smtp_port"]
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(acct["smtp_host"], smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(acct["smtp_host"], smtp_port, timeout=30)

        with server:
            if smtp_port != 465:
                server.starttls()
            server.login(acct["email_address"], acct["password"])
            server.send_message(mime_msg)

        return json.dumps({
            "sent": True,
            "to": to,
            "subject": subject,
        })

    # ------------------------------------------------------------------
    # IMAP management operations
    # ------------------------------------------------------------------

    def _mark_read(self, kw: dict) -> str:
        account = kw.get("account")
        uid = kw.get("uid")
        if not all([account, uid]):
            return json.dumps({"error": "account and uid are required for 'mark_read'"})

        acct = self._get_account(account)
        folder = kw.get("folder", "INBOX")

        with self._connect_imap(acct) as mailbox:
            mailbox.folder.set(folder)
            mailbox.flag(uid, "\\Seen", True)

        return json.dumps({"marked_read": True, "uid": uid})

    def _move_email(self, kw: dict) -> str:
        account = kw.get("account")
        uid = kw.get("uid")
        target_folder = kw.get("folder")

        if not all([account, uid, target_folder]):
            return json.dumps({
                "error": "account, uid, and folder are required for 'move_email'"
            })

        acct = self._get_account(account)

        with self._connect_imap(acct) as mailbox:
            mailbox.move(uid, target_folder)

        return json.dumps({"moved": True, "uid": uid, "folder": target_folder})

    def _delete_email(self, kw: dict) -> str:
        account = kw.get("account")
        uid = kw.get("uid")
        if not all([account, uid]):
            return json.dumps({"error": "account and uid are required for 'delete_email'"})

        acct = self._get_account(account)
        folder = kw.get("folder", "INBOX")

        with self._connect_imap(acct) as mailbox:
            mailbox.folder.set(folder)
            mailbox.delete(uid)

        return json.dumps({"deleted": True, "uid": uid})
