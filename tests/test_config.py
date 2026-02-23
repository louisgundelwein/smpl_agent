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
