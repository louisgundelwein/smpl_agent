"""Email verification reader for account signup flows."""

import imaplib
import email
import re
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EmailVerificationReader:
    """Polls an IMAP inbox for verification emails."""

    def __init__(self, email_store: Any) -> None:
        self._store = email_store

    def read_verification_code(
        self,
        email_account_name: str,
        sender_filter: str = "linkedin",
        max_wait_seconds: int = 120,
        poll_interval: int = 10,
    ) -> dict[str, str]:
        """Poll IMAP inbox for a verification email.

        Returns {"code": "...", "link": "..."} or {"error": "..."}.
        """
        acct = self._store.get(email_account_name)
        if not acct:
            return {"error": f"Email account '{email_account_name}' not found"}

        deadline = time.time() + max_wait_seconds

        while time.time() < deadline:
            try:
                result = self._check_inbox(acct, sender_filter)
                if result:
                    return result
            except Exception as exc:
                logger.warning("IMAP check failed: %s", exc)

            remaining = deadline - time.time()
            if remaining > 0:
                time.sleep(min(poll_interval, remaining))

        return {"error": "Timed out waiting for verification email"}

    def _check_inbox(
        self, acct: dict[str, Any], sender_filter: str,
    ) -> dict[str, str] | None:
        """Check IMAP inbox for matching emails. Returns result or None."""
        mailbox = imaplib.IMAP4_SSL(acct["imap_host"], acct["imap_port"])
        try:
            mailbox.login(acct["email_address"], acct["password"])
            mailbox.select("INBOX")

            _, msg_nums = mailbox.search(None, "ALL")
            if not msg_nums[0]:
                return None

            # Check newest emails first
            ids = msg_nums[0].split()
            for msg_id in reversed(ids[-20:]):
                _, msg_data = mailbox.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                from_addr = msg.get("From", "").lower()
                if sender_filter.lower() not in from_addr:
                    continue

                body = self._get_body(msg)
                if not body:
                    continue

                result: dict[str, str] = {}

                # Extract 6-digit verification code
                code_match = re.search(r"\b(\d{6})\b", body)
                if code_match:
                    result["code"] = code_match.group(1)

                # Extract verification link
                link_match = re.search(
                    r'https?://[^\s"<>]+(?:verif|confirm|activate)[^\s"<>]*',
                    body, re.IGNORECASE,
                )
                if link_match:
                    result["link"] = link_match.group(0)

                if result:
                    return result

            return None
        finally:
            try:
                mailbox.logout()
            except Exception:
                pass

    @staticmethod
    def _get_body(msg: email.message.Message) -> str:
        """Extract text body from email message."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ("text/plain", "text/html"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="replace")
        return ""
