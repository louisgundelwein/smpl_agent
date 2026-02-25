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
        transcriber: Any = None,
    ) -> None:
        self._token = token
        self._allowed_chat_ids = set(allowed_chat_ids) if allowed_chat_ids else set()
        self._base_url = BASE_URL.format(token=token)
        self._file_base_url = f"https://api.telegram.org/file/bot{token}"
        self._offset = 0
        self._bot_name: str | None = None
        self._transcriber = transcriber

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

    # Telegram rejects messages longer than this.
    _MAX_MESSAGE_LENGTH = 4096

    def _send_message(
        self, chat_id: int, text: str, reply_to_message_id: int | None = None,
    ) -> None:
        """Send a text message to a Telegram chat.

        Automatically splits messages that exceed Telegram's 4096-character
        limit.  Only the first chunk is sent as a reply; subsequent chunks
        are plain follow-up messages.

        Args:
            chat_id: Target chat.
            text: Message body.
            reply_to_message_id: If set, the first chunk is sent as a reply
                to this message ID.
        """
        if not text or not text.strip():
            text = "(empty response)"

        chunks = self._split_message(text)
        for i, chunk in enumerate(chunks):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            # Only the first chunk is a reply to the original message.
            if i == 0 and reply_to_message_id is not None:
                payload["reply_parameters"] = {"message_id": reply_to_message_id}
            try:
                resp = httpx.post(
                    f"{self._base_url}/sendMessage",
                    json=payload,
                    timeout=30.0,
                )
                if not resp.is_success:
                    logger.error(
                        "sendMessage failed (HTTP %s): %s",
                        resp.status_code,
                        resp.text[:500],
                    )
                    print(f"  [telegram] sendMessage failed (HTTP {resp.status_code}): {resp.text[:200]}")
            except Exception as exc:
                logger.error("sendMessage exception: %s", exc)
                print(f"  [telegram] sendMessage exception: {exc}")

    @classmethod
    def _split_message(cls, text: str) -> list[str]:
        """Split text into chunks that fit Telegram's message size limit.

        Tries to split on newlines first, then on spaces, and only as a
        last resort splits mid-word.
        """
        limit = cls._MAX_MESSAGE_LENGTH
        if len(text) <= limit:
            return [text]

        chunks: list[str] = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break

            # Try to find a newline to split on.
            split_at = text.rfind("\n", 0, limit)
            if split_at == -1:
                # Fall back to space.
                split_at = text.rfind(" ", 0, limit)
            if split_at == -1:
                # Hard split.
                split_at = limit

            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")

        return chunks

    def _send_typing(self, chat_id: int) -> None:
        """Send 'typing...' action indicator."""
        httpx.post(
            f"{self._base_url}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=10.0,
        )

    @staticmethod
    def _extract_reply_context(message: dict[str, Any]) -> str | None:
        """Return the text of the message being replied to, if any."""
        reply = message.get("reply_to_message")
        if not reply:
            return None
        return reply.get("text", "").strip() or None

    def _is_allowed(self, chat_id: int) -> bool:
        """Check if a chat ID is allowed (empty set = all allowed)."""
        if not self._allowed_chat_ids:
            return True
        return chat_id in self._allowed_chat_ids

    def _download_file(self, file_id: str) -> bytes:
        """Download a file from Telegram servers by file_id.

        Two-step: getFile to obtain the path, then download the content.
        """
        data = self._api("getFile", file_id=file_id)
        file_path = data["result"]["file_path"]
        url = f"{self._file_base_url}/{file_path}"
        resp = httpx.get(url, timeout=60.0)
        resp.raise_for_status()
        return resp.content

    def _handle_voice(
        self,
        message: dict[str, Any],
        chat_id: int,
        agent: Any,
        agent_lock: threading.Lock,
    ) -> None:
        """Handle a voice message: download, transcribe, pass to agent."""
        if not self._transcriber:
            self._send_message(chat_id, "Voice messages are not supported (transcription not configured).")
            return

        voice = message["voice"]
        file_id = voice["file_id"]
        duration = voice.get("duration", "?")

        print(f"  [telegram] voice message from chat {chat_id} ({duration}s)")

        try:
            audio_bytes = self._download_file(file_id)
        except Exception as exc:
            print(f"  [telegram] failed to download voice: {exc}")
            self._send_message(chat_id, "Failed to download voice message.")
            return

        try:
            text = self._transcriber.transcribe(audio_bytes)
        except Exception as exc:
            print(f"  [telegram] transcription error: {exc}")
            self._send_message(chat_id, f"Transcription failed: {exc}")
            return

        if not text.strip():
            self._send_message(chat_id, "Could not transcribe any speech from the voice message.")
            return

        print(f"  [telegram] transcribed: {text[:80]}")
        self._send_typing(chat_id)

        prefixed_text = f"[Voice message transcription]: {text}"

        reply_context = self._extract_reply_context(message)
        if reply_context:
            prefixed_text = f"[Replying to: {reply_context}]\n\n{prefixed_text}"

        msg_id = message.get("message_id")

        agent_lock.acquire()
        try:
            response = agent.run(prefixed_text)
        except Exception as exc:
            response = f"Error: {exc}"
            print(f"  [telegram] agent error: {exc}")
        finally:
            agent_lock.release()

        self._send_message(chat_id, response, reply_to_message_id=msg_id)
        print(f"  [telegram] replied to chat {chat_id}")

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

                    chat_id = message["chat"]["id"]

                    if not self._is_allowed(chat_id):
                        print(f"  [telegram] ignored message from chat {chat_id} (not in allowed list)")
                        continue

                    if message.get("voice"):
                        self._handle_voice(message, chat_id, agent, agent_lock)
                        continue

                    text = message.get("text", "").strip()
                    if not text:
                        continue

                    print(f"  [telegram] message from chat {chat_id}: {text[:80]}")
                    self._send_typing(chat_id)

                    reply_context = self._extract_reply_context(message)
                    if reply_context:
                        text = f"[Replying to: {reply_context}]\n\n{text}"

                    msg_id = message.get("message_id")

                    agent_lock.acquire()
                    try:
                        response = agent.run(text)
                    except Exception as exc:
                        response = f"Error: {exc}"
                        print(f"  [telegram] agent error: {exc}")
                    finally:
                        agent_lock.release()

                    self._send_message(chat_id, response, reply_to_message_id=msg_id)
                    print(f"  [telegram] replied to chat {chat_id}")

            except Exception as exc:
                consecutive_errors += 1
                print(f"  [telegram] poll error: {exc}")
                logger.error("Telegram poll error: %s", exc)
                time.sleep(min(5 * consecutive_errors, 60))
