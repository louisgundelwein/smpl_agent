"""Tests for src.config."""

import pytest

from src.config import Config


def test_from_env_loads_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.openai_api_key == "sk-test"
    assert config.brave_search_api_key == "BSA-test"
    assert config.openai_base_url is None


def test_default_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.openai_model == "gpt-4o"


def test_custom_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-3.5-turbo")

    config = Config.from_env(env_path="/dev/null")

    assert config.openai_model == "gpt-3.5-turbo"


def test_custom_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://my-proxy.example.com/v1")

    config = Config.from_env(env_path="/dev/null")

    assert config.openai_base_url == "https://my-proxy.example.com/v1"


def test_empty_base_url_is_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "")

    config = Config.from_env(env_path="/dev/null")

    assert config.openai_base_url is None


def test_missing_openai_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Config.from_env(env_path="/dev/null")


def test_missing_brave_key_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    with pytest.raises(ValueError, match="BRAVE_SEARCH_API_KEY"):
        Config.from_env(env_path="/dev/null")


def test_default_host_and_port(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("AGENT_HOST", raising=False)
    monkeypatch.delenv("AGENT_PORT", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.agent_host == "127.0.0.1"
    assert config.agent_port == 7600


def test_custom_host_and_port(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("AGENT_HOST", "0.0.0.0")
    monkeypatch.setenv("AGENT_PORT", "9000")

    config = Config.from_env(env_path="/dev/null")

    assert config.agent_host == "0.0.0.0"
    assert config.agent_port == 9000


def test_telegram_token(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")

    config = Config.from_env(env_path="/dev/null")

    assert config.telegram_bot_token == "123:ABC"


def test_telegram_token_empty_is_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.telegram_bot_token is None


def test_telegram_allowed_chat_ids(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "123,456,789")

    config = Config.from_env(env_path="/dev/null")

    assert config.telegram_allowed_chat_ids == [123, 456, 789]


def test_telegram_allowed_chat_ids_empty(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.telegram_allowed_chat_ids == []


def test_default_embedding_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.embedding_model == "text-embedding-3-large"


def test_custom_embedding_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")

    config = Config.from_env(env_path="/dev/null")

    assert config.embedding_model == "text-embedding-3-small"


def test_default_memory_db_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("MEMORY_DB_PATH", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.memory_db_path == "agent_memory.db"


def test_custom_memory_db_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("MEMORY_DB_PATH", "/tmp/test.db")

    config = Config.from_env(env_path="/dev/null")

    assert config.memory_db_path == "/tmp/test.db"


def test_default_soul_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("SOUL_PATH", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.soul_path == "SOUL.md"


def test_custom_soul_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("SOUL_PATH", "/custom/path/soul.md")

    config = Config.from_env(env_path="/dev/null")

    assert config.soul_path == "/custom/path/soul.md"


def test_default_shell_command_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("SHELL_COMMAND_TIMEOUT", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.shell_command_timeout == 30


def test_custom_shell_command_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("SHELL_COMMAND_TIMEOUT", "60")

    config = Config.from_env(env_path="/dev/null")

    assert config.shell_command_timeout == 60


def test_default_shell_max_output(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("SHELL_MAX_OUTPUT", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.shell_max_output == 50000


def test_custom_shell_max_output(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("SHELL_MAX_OUTPUT", "100000")

    config = Config.from_env(env_path="/dev/null")

    assert config.shell_max_output == 100000


def test_default_context_max_tokens(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("CONTEXT_MAX_TOKENS", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.context_max_tokens == 100000


def test_custom_context_max_tokens(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("CONTEXT_MAX_TOKENS", "32000")

    config = Config.from_env(env_path="/dev/null")

    assert config.context_max_tokens == 32000


def test_default_context_preserve_recent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("CONTEXT_PRESERVE_RECENT", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.context_preserve_recent == 10


def test_custom_context_preserve_recent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("CONTEXT_PRESERVE_RECENT", "20")

    config = Config.from_env(env_path="/dev/null")

    assert config.context_preserve_recent == 20


def test_default_codex_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("CODEX_TIMEOUT", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.codex_timeout == 300


def test_custom_codex_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("CODEX_TIMEOUT", "600")

    config = Config.from_env(env_path="/dev/null")

    assert config.codex_timeout == 600


def test_default_codex_max_output(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("CODEX_MAX_OUTPUT", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.codex_max_output == 50000


def test_custom_codex_max_output(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("CODEX_MAX_OUTPUT", "100000")

    config = Config.from_env(env_path="/dev/null")

    assert config.codex_max_output == 100000


def test_default_github_token(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.github_token is None


def test_custom_github_token(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")

    config = Config.from_env(env_path="/dev/null")

    assert config.github_token == "ghp_test123"


def test_default_history_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.delenv("HISTORY_PATH", raising=False)

    config = Config.from_env(env_path="/dev/null")

    assert config.history_path == "conversation_history.json"


def test_custom_history_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSA-test")
    monkeypatch.setenv("HISTORY_PATH", "/tmp/my_history.json")

    config = Config.from_env(env_path="/dev/null")

    assert config.history_path == "/tmp/my_history.json"
