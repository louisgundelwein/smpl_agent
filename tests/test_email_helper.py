"""Tests for EmailVerificationReader."""

import json
from unittest.mock import MagicMock, patch, PropertyMock
import email
from email.mime.text import MIMEText

import pytest

from src.marketing.email_helper import EmailVerificationReader


@pytest.fixture
def mock_email_store():
    store = MagicMock()
    store.get.return_value = {
        "email_address": "user@test.com",
        "password": "pass123",
        "imap_host": "imap.test.com",
        "imap_port": 993,
    }
    return store


@pytest.fixture
def reader(mock_email_store):
    return EmailVerificationReader(mock_email_store)


def _make_email(from_addr: str, body: str) -> bytes:
    msg = MIMEText(body)
    msg["From"] = from_addr
    msg["Subject"] = "Verification"
    return msg.as_bytes()


class TestReadVerificationCode:
    def test_success_with_code(self, reader, mock_email_store):
        raw = _make_email("noreply@linkedin.com", "Your verification code is 482913.")

        with patch("src.marketing.email_helper.imaplib.IMAP4_SSL") as mock_imap_cls:
            mock_imap = MagicMock()
            mock_imap_cls.return_value = mock_imap
            mock_imap.search.return_value = ("OK", [b"1"])
            mock_imap.fetch.return_value = ("OK", [(b"1", raw)])

            result = reader.read_verification_code(
                "work", max_wait_seconds=1, poll_interval=1,
            )

        assert result["code"] == "482913"

    def test_success_with_link(self, reader, mock_email_store):
        body = 'Click here to verify: https://www.linkedin.com/verify?token=abc123'
        raw = _make_email("security@linkedin.com", body)

        with patch("src.marketing.email_helper.imaplib.IMAP4_SSL") as mock_imap_cls:
            mock_imap = MagicMock()
            mock_imap_cls.return_value = mock_imap
            mock_imap.search.return_value = ("OK", [b"1"])
            mock_imap.fetch.return_value = ("OK", [(b"1", raw)])

            result = reader.read_verification_code(
                "work", max_wait_seconds=1, poll_interval=1,
            )

        assert "link" in result
        assert "verify" in result["link"]

    def test_timeout(self, reader, mock_email_store):
        with patch("src.marketing.email_helper.imaplib.IMAP4_SSL") as mock_imap_cls:
            mock_imap = MagicMock()
            mock_imap_cls.return_value = mock_imap
            mock_imap.search.return_value = ("OK", [b""])

            result = reader.read_verification_code(
                "work", max_wait_seconds=1, poll_interval=1,
            )

        assert "error" in result
        assert "Timed out" in result["error"]

    def test_email_account_not_found(self, mock_email_store):
        mock_email_store.get.return_value = None
        reader = EmailVerificationReader(mock_email_store)
        result = reader.read_verification_code("nonexistent", max_wait_seconds=1)
        assert "error" in result
        assert "not found" in result["error"]

    def test_filters_by_sender(self, reader, mock_email_store):
        # Email from wrong sender should be skipped
        raw = _make_email("noreply@github.com", "Your code is 123456.")

        with patch("src.marketing.email_helper.imaplib.IMAP4_SSL") as mock_imap_cls:
            mock_imap = MagicMock()
            mock_imap_cls.return_value = mock_imap
            mock_imap.search.return_value = ("OK", [b"1"])
            mock_imap.fetch.return_value = ("OK", [(b"1", raw)])

            result = reader.read_verification_code(
                "work", sender_filter="linkedin",
                max_wait_seconds=1, poll_interval=1,
            )

        assert "error" in result
        assert "Timed out" in result["error"]
