"""Tests for src.telegram using respx to mock Telegram API."""

import json
import threading
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from src.telegram import TelegramBot

TOKEN = "123:FAKE"
BASE = f"https://api.telegram.org/bot{TOKEN}"


def _make_update(update_id, chat_id, text):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": chat_id},
            "text": text,
        },
    }


def _run_one_poll(bot, agent, agent_lock, updates_response):
    """Run exactly one iteration of poll_loop, then stop."""
    call_count = 0

    # Track getUpdates calls — return data on first, raise to stop on second
    original_api = bot._api

    def mock_api(method, **params):
        nonlocal call_count
        if method == "getUpdates":
            call_count += 1
            if call_count == 1:
                return updates_response
            raise KeyboardInterrupt("stop")
        return original_api(method, **params)

    bot._api = mock_api

    try:
        bot.poll_loop(agent, agent_lock)
    except KeyboardInterrupt:
        pass


@respx.mock
def test_poll_and_respond():
    bot = TelegramBot(token=TOKEN)
    agent = MagicMock()
    agent.run.return_value = "Hello from agent!"
    lock = threading.Lock()

    send_route = respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    typing_route = respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [_make_update(100, 42, "hi agent")]}
    _run_one_poll(bot, agent, lock, updates)

    agent.run.assert_called_once_with("hi agent")
    assert send_route.called
    payload = json.loads(send_route.calls[0].request.content)
    assert payload["text"] == "Hello from agent!"
    # Bot should reply to the incoming message.
    assert payload["reply_parameters"] == {"message_id": 100}


@respx.mock
def test_typing_action_sent():
    bot = TelegramBot(token=TOKEN)
    agent = MagicMock()
    agent.run.return_value = "response"
    lock = threading.Lock()

    respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    typing_route = respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [_make_update(100, 42, "test")]}
    _run_one_poll(bot, agent, lock, updates)

    assert typing_route.called


@respx.mock
def test_offset_updated():
    bot = TelegramBot(token=TOKEN)
    agent = MagicMock()
    agent.run.return_value = "ok"
    lock = threading.Lock()

    respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [_make_update(200, 42, "test")]}
    _run_one_poll(bot, agent, lock, updates)

    assert bot._offset == 201


@respx.mock
def test_allowed_chat_ids_filters():
    bot = TelegramBot(token=TOKEN, allowed_chat_ids=[42])
    agent = MagicMock()
    agent.run.return_value = "ok"
    lock = threading.Lock()

    respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {
        "ok": True,
        "result": [
            _make_update(100, 999, "from unauthorized"),
            _make_update(101, 42, "from allowed"),
        ],
    }
    _run_one_poll(bot, agent, lock, updates)

    # Only the allowed message should be processed
    agent.run.assert_called_once_with("from allowed")


def test_empty_updates():
    bot = TelegramBot(token=TOKEN)
    agent = MagicMock()
    lock = threading.Lock()

    updates = {"ok": True, "result": []}
    _run_one_poll(bot, agent, lock, updates)

    agent.run.assert_not_called()


def test_is_allowed_empty_set_allows_all():
    bot = TelegramBot(token=TOKEN, allowed_chat_ids=[])
    assert bot._is_allowed(12345) is True


def test_is_allowed_with_ids():
    bot = TelegramBot(token=TOKEN, allowed_chat_ids=[42, 99])
    assert bot._is_allowed(42) is True
    assert bot._is_allowed(99) is True
    assert bot._is_allowed(100) is False


@respx.mock
def test_verify_success():
    bot = TelegramBot(token=TOKEN)
    respx.get(f"{BASE}/getMe").mock(
        return_value=httpx.Response(
            200,
            json={"ok": True, "result": {"id": 123, "username": "test_bot"}},
        )
    )
    name = bot.verify()
    assert name == "test_bot"
    assert bot._bot_name == "test_bot"


@respx.mock
def test_verify_invalid_token():
    bot = TelegramBot(token="bad:token")
    bad_base = "https://api.telegram.org/botbad:token"
    respx.get(f"{bad_base}/getMe").mock(
        return_value=httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        bot.verify()


# --- Voice message tests ---

FILE_BASE = f"https://api.telegram.org/file/bot{TOKEN}"


def _make_voice_update(update_id, chat_id, file_id="voice_file_123", duration=5):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": chat_id},
            "voice": {
                "file_id": file_id,
                "duration": duration,
                "mime_type": "audio/ogg",
            },
        },
    }


@respx.mock
def test_voice_message_transcribed_and_sent():
    """Voice message is downloaded, transcribed, and response sent."""
    transcriber = MagicMock()
    transcriber.transcribe.return_value = "hello from voice"

    bot = TelegramBot(token=TOKEN, transcriber=transcriber)
    agent = MagicMock()
    agent.run.return_value = "I heard you"
    lock = threading.Lock()

    # Mock getFile API
    respx.get(f"{BASE}/getFile").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "result": {"file_path": "voice/file_0.ogg"},
        })
    )
    # Mock file download
    respx.get(f"{FILE_BASE}/voice/file_0.ogg").mock(
        return_value=httpx.Response(200, content=b"fake-ogg-bytes")
    )
    send_route = respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [_make_voice_update(100, 42)]}
    _run_one_poll(bot, agent, lock, updates)

    transcriber.transcribe.assert_called_once_with(b"fake-ogg-bytes")
    agent.run.assert_called_once_with("[Voice message transcription]: hello from voice")
    assert send_route.called


@respx.mock
def test_voice_without_transcriber_sends_error():
    """When no transcriber is configured, voice messages get an error reply."""
    bot = TelegramBot(token=TOKEN)  # No transcriber
    agent = MagicMock()
    lock = threading.Lock()

    send_route = respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [_make_voice_update(100, 42)]}
    _run_one_poll(bot, agent, lock, updates)

    agent.run.assert_not_called()
    assert send_route.called
    body = send_route.calls[0].request.content
    assert b"not supported" in body


@respx.mock
def test_voice_from_unauthorized_chat_ignored():
    """Voice messages from unauthorized chats are ignored."""
    transcriber = MagicMock()
    bot = TelegramBot(token=TOKEN, allowed_chat_ids=[42], transcriber=transcriber)
    agent = MagicMock()
    lock = threading.Lock()

    updates = {"ok": True, "result": [_make_voice_update(100, 999)]}
    _run_one_poll(bot, agent, lock, updates)

    transcriber.transcribe.assert_not_called()
    agent.run.assert_not_called()


# --- Reply context tests ---


def _make_reply_update(update_id, chat_id, text, replied_text):
    """Build an update where the user replies to an earlier message."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": chat_id},
            "text": text,
            "reply_to_message": {
                "message_id": update_id - 1,
                "chat": {"id": chat_id},
                "text": replied_text,
            },
        },
    }


@respx.mock
def test_reply_context_forwarded_to_agent():
    """When user replies to a message, the agent receives the quoted text as context."""
    bot = TelegramBot(token=TOKEN)
    agent = MagicMock()
    agent.run.return_value = "got it"
    lock = threading.Lock()

    respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [
        _make_reply_update(101, 42, "what did you mean?", "The capital of France is Paris."),
    ]}
    _run_one_poll(bot, agent, lock, updates)

    agent.run.assert_called_once_with(
        "[Replying to: The capital of France is Paris.]\n\nwhat did you mean?"
    )


@respx.mock
def test_no_reply_context_when_no_reply():
    """A normal message (no reply) is sent to the agent without any prefix."""
    bot = TelegramBot(token=TOKEN)
    agent = MagicMock()
    agent.run.return_value = "ok"
    lock = threading.Lock()

    respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [_make_update(100, 42, "plain message")]}
    _run_one_poll(bot, agent, lock, updates)

    agent.run.assert_called_once_with("plain message")


@respx.mock
def test_reply_parameters_in_send_payload():
    """Bot response includes reply_parameters pointing to the user's message."""
    bot = TelegramBot(token=TOKEN)
    agent = MagicMock()
    agent.run.return_value = "reply"
    lock = threading.Lock()

    send_route = respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [_make_update(555, 42, "test")]}
    _run_one_poll(bot, agent, lock, updates)

    payload = json.loads(send_route.calls[0].request.content)
    assert payload["reply_parameters"] == {"message_id": 555}


@respx.mock
def test_voice_with_reply_context():
    """Voice message sent as reply includes context from the quoted message."""
    transcriber = MagicMock()
    transcriber.transcribe.return_value = "voice text"

    bot = TelegramBot(token=TOKEN, transcriber=transcriber)
    agent = MagicMock()
    agent.run.return_value = "understood"
    lock = threading.Lock()

    voice_update = {
        "update_id": 200,
        "message": {
            "message_id": 200,
            "chat": {"id": 42},
            "voice": {"file_id": "vf1", "duration": 3, "mime_type": "audio/ogg"},
            "reply_to_message": {
                "message_id": 190,
                "chat": {"id": 42},
                "text": "Tell me more about this",
            },
        },
    }

    respx.get(f"{BASE}/getFile").mock(
        return_value=httpx.Response(200, json={
            "ok": True, "result": {"file_path": "voice/f.ogg"},
        })
    )
    respx.get(f"{FILE_BASE}/voice/f.ogg").mock(
        return_value=httpx.Response(200, content=b"audio")
    )
    send_route = respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [voice_update]}
    _run_one_poll(bot, agent, lock, updates)

    agent.run.assert_called_once_with(
        "[Replying to: Tell me more about this]\n\n[Voice message transcription]: voice text"
    )
    payload = json.loads(send_route.calls[0].request.content)
    assert payload["reply_parameters"] == {"message_id": 200}


def test_extract_reply_context_no_reply():
    """_extract_reply_context returns None when no reply_to_message."""
    bot = TelegramBot(token=TOKEN)
    assert bot._extract_reply_context({"text": "hello"}) is None


def test_extract_reply_context_with_reply():
    """_extract_reply_context returns the quoted text."""
    bot = TelegramBot(token=TOKEN)
    msg = {
        "text": "follow up",
        "reply_to_message": {"message_id": 1, "text": "original text"},
    }
    assert bot._extract_reply_context(msg) == "original text"


def test_extract_reply_context_empty_text():
    """_extract_reply_context returns None when quoted message has no text (e.g. photo)."""
    bot = TelegramBot(token=TOKEN)
    msg = {
        "text": "what's this?",
        "reply_to_message": {"message_id": 1},
    }
    assert bot._extract_reply_context(msg) is None


# --- Message splitting tests ---


def test_split_message_short():
    """Short messages are returned as a single chunk."""
    chunks = TelegramBot._split_message("Hello!")
    assert chunks == ["Hello!"]


def test_split_message_at_limit():
    """Message exactly at the limit is a single chunk."""
    text = "a" * 4096
    chunks = TelegramBot._split_message(text)
    assert chunks == [text]


def test_split_message_long_splits_on_newline():
    """Long messages are split on newlines when possible."""
    line = "x" * 2000
    text = f"{line}\n{line}\n{line}"  # ~6002 chars
    chunks = TelegramBot._split_message(text)
    assert len(chunks) == 2
    assert all(len(c) <= 4096 for c in chunks)
    # First chunk should split at the second newline (pos 4001).
    assert chunks[0] == f"{line}\n{line}"
    assert chunks[1] == line


def test_split_message_long_splits_on_space():
    """Falls back to space splitting when no newlines."""
    word = "hello "
    text = word * 1000  # 6000 chars, no newlines
    chunks = TelegramBot._split_message(text)
    assert len(chunks) >= 2
    assert all(len(c) <= 4096 for c in chunks)


def test_split_message_hard_split():
    """Hard-splits when no newline or space is available."""
    text = "a" * 5000  # no spaces or newlines
    chunks = TelegramBot._split_message(text)
    assert len(chunks) == 2
    assert chunks[0] == "a" * 4096
    assert chunks[1] == "a" * 904


@respx.mock
def test_empty_response_replaced():
    """Empty agent response is replaced with a placeholder."""
    bot = TelegramBot(token=TOKEN)
    agent = MagicMock()
    agent.run.return_value = ""
    lock = threading.Lock()

    send_route = respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [_make_update(100, 42, "hi")]}
    _run_one_poll(bot, agent, lock, updates)

    payload = json.loads(send_route.calls[0].request.content)
    assert payload["text"] == "(empty response)"


@respx.mock
def test_long_response_split_into_chunks():
    """A response exceeding 4096 chars is split into multiple messages."""
    bot = TelegramBot(token=TOKEN)
    agent = MagicMock()
    agent.run.return_value = "a" * 5000
    lock = threading.Lock()

    send_route = respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post(f"{BASE}/sendChatAction").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    updates = {"ok": True, "result": [_make_update(100, 42, "hi")]}
    _run_one_poll(bot, agent, lock, updates)

    assert send_route.call_count == 2
    first = json.loads(send_route.calls[0].request.content)
    second = json.loads(send_route.calls[1].request.content)
    # Only the first chunk should be a reply.
    assert "reply_parameters" in first
    assert "reply_parameters" not in second


@respx.mock
def test_send_message_logs_error(capsys):
    """sendMessage errors are logged, not silently swallowed."""
    bot = TelegramBot(token=TOKEN)

    respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(400, json={
            "ok": False,
            "description": "Bad Request: message is too long",
        })
    )

    bot._send_message(42, "test")

    captured = capsys.readouterr()
    assert "sendMessage failed" in captured.out
    assert "400" in captured.out
