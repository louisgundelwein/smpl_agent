"""Tests for src.tools.email — EmailTool with mocked IMAP/SMTP."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.email_store import EmailAccountStore
from src.tools.email import EmailTool, _strip_html, _body_text


@pytest.fixture()
def store():
    s = EmailAccountStore(db_path=":memory:")
    yield s
    s.close()


@pytest.fixture()
def tool(store):
    return EmailTool(store=store)


@pytest.fixture()
def store_with_acct(store):
    store.add(
        name="work",
        email_address="alice@example.com",
        password="secret",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
    )
    return store


@pytest.fixture()
def tool_with_acct(store_with_acct):
    return EmailTool(store=store_with_acct)


def _mock_message(
    uid="123", from_="bob@example.com", to=("alice@example.com",),
    cc=(), subject="Test Subject", text="Hello world", html="",
    date=None, flags=("\\Seen",), attachments=(),
):
    """Create a mock imap_tools MailMessage."""
    msg = MagicMock()
    msg.uid = uid
    msg.from_ = from_
    msg.to = to
    msg.cc = cc
    msg.subject = subject
    msg.text = text
    msg.html = html
    msg.date = date or datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    msg.flags = flags
    msg.attachments = list(attachments)
    return msg


# ------------------------------------------------------------------
# Account management
# ------------------------------------------------------------------


class TestAddAccount:
    def test_success(self, tool):
        result = json.loads(tool.execute(
            action="add_account",
            name="work",
            email_address="a@b.com",
            password="p",
            imap_host="imap.b.com",
            smtp_host="smtp.b.com",
        ))
        assert result["added"] is True
        assert result["total_accounts"] == 1

    def test_missing_fields(self, tool):
        result = json.loads(tool.execute(action="add_account", name="x"))
        assert "error" in result

    def test_duplicate_name(self, tool):
        tool.execute(
            action="add_account", name="a",
            email_address="a@a", password="p",
            imap_host="i", smtp_host="s",
        )
        result = json.loads(tool.execute(
            action="add_account", name="a",
            email_address="b@b", password="p",
            imap_host="i", smtp_host="s",
        ))
        assert "error" in result


class TestListAccounts:
    def test_empty(self, tool):
        result = json.loads(tool.execute(action="list_accounts"))
        assert result["count"] == 0

    def test_with_accounts(self, tool_with_acct):
        result = json.loads(tool_with_acct.execute(action="list_accounts"))
        assert result["count"] == 1
        assert "password" not in result["accounts"][0]


class TestRemoveAccount:
    def test_success(self, tool_with_acct):
        result = json.loads(tool_with_acct.execute(
            action="remove_account", name="work",
        ))
        assert result["removed"] is True

    def test_not_found(self, tool):
        result = json.loads(tool.execute(
            action="remove_account", name="ghost",
        ))
        assert result["removed"] is False

    def test_missing_name(self, tool):
        result = json.loads(tool.execute(action="remove_account"))
        assert "error" in result


# ------------------------------------------------------------------
# IMAP operations (mocked)
# ------------------------------------------------------------------


class TestListFolders:
    @patch("src.tools.email.MailBox")
    def test_success(self, mock_mb_cls, tool_with_acct):
        mock_mb = MagicMock()
        mock_mb_cls.return_value = mock_mb
        mock_mb.__enter__ = MagicMock(return_value=mock_mb)
        mock_mb.__exit__ = MagicMock(return_value=False)

        folder1 = MagicMock()
        folder1.name = "INBOX"
        folder1.flags = ("\\HasNoChildren",)
        folder2 = MagicMock()
        folder2.name = "Sent"
        folder2.flags = ("\\Sent",)
        mock_mb.folder.list.return_value = [folder1, folder2]

        result = json.loads(tool_with_acct.execute(
            action="list_folders", account="work",
        ))
        assert result["count"] == 2
        assert result["folders"][0]["name"] == "INBOX"

    def test_missing_account(self, tool):
        result = json.loads(tool.execute(action="list_folders"))
        assert "error" in result


class TestReadEmails:
    @patch("src.tools.email.MailBox")
    def test_success(self, mock_mb_cls, tool_with_acct):
        mock_mb = MagicMock()
        mock_mb_cls.return_value = mock_mb
        mock_mb.__enter__ = MagicMock(return_value=mock_mb)
        mock_mb.__exit__ = MagicMock(return_value=False)
        mock_mb.fetch.return_value = [
            _mock_message(uid="1", subject="Hello"),
            _mock_message(uid="2", subject="World"),
        ]

        result = json.loads(tool_with_acct.execute(
            action="read_emails", account="work", limit=5,
        ))
        assert result["count"] == 2
        assert result["emails"][0]["subject"] == "Hello"
        assert result["emails"][0]["uid"] == "1"

    @patch("src.tools.email.MailBox")
    def test_unread_only(self, mock_mb_cls, tool_with_acct):
        mock_mb = MagicMock()
        mock_mb_cls.return_value = mock_mb
        mock_mb.__enter__ = MagicMock(return_value=mock_mb)
        mock_mb.__exit__ = MagicMock(return_value=False)
        mock_mb.fetch.return_value = []

        tool_with_acct.execute(
            action="read_emails", account="work", unread_only=True,
        )
        # Verify fetch was called (criteria is an AND object)
        mock_mb.fetch.assert_called_once()

    def test_missing_account(self, tool):
        result = json.loads(tool.execute(action="read_emails"))
        assert "error" in result

    @patch("src.tools.email.MailBox")
    def test_account_not_found(self, mock_mb_cls, tool):
        result = json.loads(tool.execute(
            action="read_emails", account="nonexistent",
        ))
        assert "error" in result
        assert "not found" in result["error"]


class TestSearchEmails:
    @patch("src.tools.email.MailBox")
    def test_by_sender(self, mock_mb_cls, tool_with_acct):
        mock_mb = MagicMock()
        mock_mb_cls.return_value = mock_mb
        mock_mb.__enter__ = MagicMock(return_value=mock_mb)
        mock_mb.__exit__ = MagicMock(return_value=False)
        mock_mb.fetch.return_value = [
            _mock_message(uid="10", from_="boss@work.com", subject="Review"),
        ]

        result = json.loads(tool_with_acct.execute(
            action="search_emails", account="work", from_="boss@work.com",
        ))
        assert result["count"] == 1
        assert result["emails"][0]["from"] == "boss@work.com"

    def test_missing_account(self, tool):
        result = json.loads(tool.execute(action="search_emails"))
        assert "error" in result


class TestReadEmail:
    @patch("src.tools.email.MailBox")
    def test_success(self, mock_mb_cls, tool_with_acct):
        mock_mb = MagicMock()
        mock_mb_cls.return_value = mock_mb
        mock_mb.__enter__ = MagicMock(return_value=mock_mb)
        mock_mb.__exit__ = MagicMock(return_value=False)
        mock_mb.fetch.return_value = [
            _mock_message(uid="42", text="Full body text here"),
        ]

        result = json.loads(tool_with_acct.execute(
            action="read_email", account="work", uid="42",
        ))
        assert result["email"]["uid"] == "42"
        assert "Full body text here" in result["email"]["body"]

    @patch("src.tools.email.MailBox")
    def test_not_found(self, mock_mb_cls, tool_with_acct):
        mock_mb = MagicMock()
        mock_mb_cls.return_value = mock_mb
        mock_mb.__enter__ = MagicMock(return_value=mock_mb)
        mock_mb.__exit__ = MagicMock(return_value=False)
        mock_mb.fetch.return_value = []

        result = json.loads(tool_with_acct.execute(
            action="read_email", account="work", uid="999",
        ))
        assert "error" in result

    def test_missing_fields(self, tool_with_acct):
        result = json.loads(tool_with_acct.execute(action="read_email"))
        assert "error" in result


# ------------------------------------------------------------------
# SMTP send (mocked)
# ------------------------------------------------------------------


class TestSendEmail:
    @patch("src.tools.email.smtplib.SMTP")
    def test_success(self, mock_smtp_cls, tool_with_acct):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        result = json.loads(tool_with_acct.execute(
            action="send_email",
            account="work",
            to="bob@example.com",
            subject="Test",
            body="Hello Bob!",
        ))
        assert result["sent"] is True
        assert result["to"] == "bob@example.com"
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()

    @patch("src.tools.email.smtplib.SMTP_SSL")
    def test_ssl_port_465(self, mock_smtp_ssl_cls, store):
        store.add(
            name="ssl", email_address="a@a", password="p",
            imap_host="i", smtp_host="s", smtp_port=465,
        )
        tool = EmailTool(store=store)

        mock_server = MagicMock()
        mock_smtp_ssl_cls.return_value = mock_server
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        result = json.loads(tool.execute(
            action="send_email",
            account="ssl",
            to="b@b",
            subject="S",
            body="B",
        ))
        assert result["sent"] is True
        mock_smtp_ssl_cls.assert_called_once()

    def test_missing_fields(self, tool_with_acct):
        result = json.loads(tool_with_acct.execute(
            action="send_email", account="work",
        ))
        assert "error" in result


# ------------------------------------------------------------------
# IMAP management operations
# ------------------------------------------------------------------


class TestMarkRead:
    @patch("src.tools.email.MailBox")
    def test_success(self, mock_mb_cls, tool_with_acct):
        mock_mb = MagicMock()
        mock_mb_cls.return_value = mock_mb
        mock_mb.__enter__ = MagicMock(return_value=mock_mb)
        mock_mb.__exit__ = MagicMock(return_value=False)

        result = json.loads(tool_with_acct.execute(
            action="mark_read", account="work", uid="5",
        ))
        assert result["marked_read"] is True
        mock_mb.flag.assert_called_once_with("5", "\\Seen", True)

    def test_missing_fields(self, tool):
        result = json.loads(tool.execute(action="mark_read"))
        assert "error" in result


class TestMoveEmail:
    @patch("src.tools.email.MailBox")
    def test_success(self, mock_mb_cls, tool_with_acct):
        mock_mb = MagicMock()
        mock_mb_cls.return_value = mock_mb
        mock_mb.__enter__ = MagicMock(return_value=mock_mb)
        mock_mb.__exit__ = MagicMock(return_value=False)

        result = json.loads(tool_with_acct.execute(
            action="move_email", account="work", uid="7", folder="Archive",
        ))
        assert result["moved"] is True
        assert result["folder"] == "Archive"
        mock_mb.move.assert_called_once_with("7", "Archive")

    def test_missing_fields(self, tool):
        result = json.loads(tool.execute(action="move_email", account="work"))
        assert "error" in result


class TestDeleteEmail:
    @patch("src.tools.email.MailBox")
    def test_success(self, mock_mb_cls, tool_with_acct):
        mock_mb = MagicMock()
        mock_mb_cls.return_value = mock_mb
        mock_mb.__enter__ = MagicMock(return_value=mock_mb)
        mock_mb.__exit__ = MagicMock(return_value=False)

        result = json.loads(tool_with_acct.execute(
            action="delete_email", account="work", uid="9",
        ))
        assert result["deleted"] is True
        mock_mb.delete.assert_called_once_with("9")

    def test_missing_fields(self, tool):
        result = json.loads(tool.execute(action="delete_email"))
        assert "error" in result


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------


class TestStripHtml:
    def test_strips_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self):
        assert _strip_html("<div>  a   b  </div>") == "a b"


class TestBodyText:
    def test_prefers_plaintext(self):
        msg = _mock_message(text="plain", html="<b>html</b>")
        assert _body_text(msg) == "plain"

    def test_falls_back_to_html(self):
        msg = _mock_message(text="", html="<b>html content</b>")
        assert "html content" in _body_text(msg)

    def test_truncates(self):
        msg = _mock_message(text="x" * 1000)
        result = _body_text(msg, max_len=100)
        assert len(result) == 101  # 100 chars + "…"
        assert result.endswith("…")


class TestUnknownAction:
    def test_unknown(self, tool):
        result = json.loads(tool.execute(action="bogus"))
        assert "error" in result
