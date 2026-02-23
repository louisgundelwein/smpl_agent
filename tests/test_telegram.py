"""Tests for src.telegram using respx to mock Telegram API."""

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
    send_call = send_route.calls[0]
    body = send_call.request.content
    assert b"Hello from agent!" in body


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
