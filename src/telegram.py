"""Telegram Bot integration using httpx directly (no extra dependencies)."""

import logging
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.telegram.org/bot{token}"


class TelegramBot:
    """Polls Telegram for messages and forwards them to the Agent.

    Uses long polling via getUpdates. Only the final text response
    is sent back (tool events are not forwarded to Telegram).
    """

    def __init__(
        self,
        token: str,
        allowed_chat_ids: list[int] | None = None,
    ) -> None:
        self._token = token
        self._allowed_chat_ids = set(allowed_chat_ids) if allowed_chat_ids else set()
        self._base_url = BASE_URL.format(token=token)
        self._offset = 0
        self._bot_name: str | None = None

    def verify(self) -> str:
        """Call getMe to verify the token works. Returns the bot username.

        Raises httpx.HTTPStatusError if the token is invalid.
        """
        data = self._api("getMe")
        username = data.get("result", {}).get("username", "unknown")
        self._bot_name = username
        return username

    def _api(self, method: str, **params: Any) -> dict[str, Any]:
        """Call a Telegram Bot API method."""
        url = f"{self._base_url}/{method}"
        resp = httpx.get(url, params=params, timeout=60.0)
        resp.raise_for_status()
        return resp.json()

    def _send_message(self, chat_id: int, text: str) -> None:
        """Send a text message to a Telegram chat."""
        httpx.post(
            f"{self._base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=30.0,
        )

    def _send_typing(self, chat_id: int) -> None:
        """Send 'typing...' action indicator."""
        httpx.post(
            f"{self._base_url}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=10.0,
        )

    def _is_allowed(self, chat_id: int) -> bool:
        """Check if a chat ID is allowed (empty set = all allowed)."""
        if not self._allowed_chat_ids:
            return True
        return chat_id in self._allowed_chat_ids

    def poll_loop(self, agent: Any, agent_lock: threading.Lock) -> None:
        """Long-polling loop — runs in a daemon thread.

        Args:
            agent: The Agent instance to forward messages to.
            agent_lock: Lock to serialize agent.run() calls.
        """
        logger.info("Telegram polling started.")
        consecutive_errors = 0

        while True:
            try:
                data = self._api(
                    "getUpdates",
                    offset=self._offset,
                    timeout=30,
                )
                consecutive_errors = 0
                updates = data.get("result", [])

                for update in updates:
                    self._offset = update["update_id"] + 1

                    message = update.get("message")
                    if not message:
                        continue

                    text = message.get("text", "").strip()
                    chat_id = message["chat"]["id"]

                    if not text:
                        continue

                    if not self._is_allowed(chat_id):
                        print(f"  [telegram] ignored message from chat {chat_id} (not in allowed list)")
                        continue

                    print(f"  [telegram] message from chat {chat_id}: {text[:80]}")
                    self._send_typing(chat_id)

                    agent_lock.acquire()
                    try:
                        response = agent.run(text)
                    except Exception as exc:
                        response = f"Error: {exc}"
                        print(f"  [telegram] agent error: {exc}")
                    finally:
                        agent_lock.release()

                    self._send_message(chat_id, response)
                    print(f"  [telegram] replied to chat {chat_id}")

            except Exception as exc:
                consecutive_errors += 1
                print(f"  [telegram] poll error: {exc}")
                logger.error("Telegram poll error: %s", exc)
                time.sleep(min(5 * consecutive_errors, 60))
