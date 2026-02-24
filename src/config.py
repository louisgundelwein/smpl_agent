"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Immutable application configuration."""

    openai_api_key: str
    openai_model: str
    openai_base_url: str | None
    brave_search_api_key: str
    agent_host: str
    agent_port: int
    telegram_bot_token: str | None
    telegram_allowed_chat_ids: list[int]
    embedding_model: str
    memory_db_path: str
    soul_path: str
    shell_command_timeout: int
    shell_max_output: int
    context_max_tokens: int
    context_preserve_recent: int
    codex_timeout: int
    codex_max_output: int
    github_token: str | None
    history_path: str
    whisper_model: str
    max_tool_rounds: int
    daemon_pid_path: str
    daemon_log_path: str
    scheduler_db_path: str
    scheduler_poll_interval: int
    scheduler_tasks: str
    repos_db_path: str

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "Config":
        """Load configuration from .env file and environment.

        Raises:
            ValueError: If required environment variables are missing.
        """
        load_dotenv(env_path)

        openai_key = os.getenv("OPENAI_API_KEY")
        brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        base_url = os.getenv("OPENAI_BASE_URL") or None
        agent_host = os.getenv("AGENT_HOST", "127.0.0.1")
        agent_port = int(os.getenv("AGENT_PORT", "7600"))
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN") or None

        raw_ids = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
        telegram_chat_ids = [
            int(x.strip()) for x in raw_ids.split(",") if x.strip()
        ]

        embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
        memory_db_path = os.getenv("MEMORY_DB_PATH", "agent_memory.db")
        soul_path = os.getenv("SOUL_PATH", "SOUL.md")
        shell_command_timeout = int(os.getenv("SHELL_COMMAND_TIMEOUT", "30"))
        shell_max_output = int(os.getenv("SHELL_MAX_OUTPUT", "50000"))
        context_max_tokens = int(os.getenv("CONTEXT_MAX_TOKENS", "100000"))
        context_preserve_recent = int(os.getenv("CONTEXT_PRESERVE_RECENT", "10"))
        codex_timeout = int(os.getenv("CODEX_TIMEOUT", "300"))
        codex_max_output = int(os.getenv("CODEX_MAX_OUTPUT", "50000"))
        github_token = os.getenv("GITHUB_TOKEN") or None
        history_path = os.getenv("HISTORY_PATH", "conversation_history.json")
        whisper_model = os.getenv("WHISPER_MODEL", "openai/whisper-large-v3-turbo")
        max_tool_rounds = int(os.getenv("MAX_TOOL_ROUNDS", "25"))
        daemon_pid_path = os.getenv("DAEMON_PID_PATH", "agent.pid")
        daemon_log_path = os.getenv("DAEMON_LOG_PATH", "agent.log")
        scheduler_db_path = os.getenv("SCHEDULER_DB_PATH", "scheduler.db")
        scheduler_poll_interval = int(os.getenv("SCHEDULER_POLL_INTERVAL", "30"))
        scheduler_tasks = os.getenv("SCHEDULER_TASKS", "")
        repos_db_path = os.getenv("REPOS_DB_PATH", "repos.db")

        if not openai_key:
            raise ValueError("OPENAI_API_KEY is required")
        if not brave_key:
            raise ValueError("BRAVE_SEARCH_API_KEY is required")

        return cls(
            openai_api_key=openai_key,
            openai_model=model,
            openai_base_url=base_url,
            brave_search_api_key=brave_key,
            agent_host=agent_host,
            agent_port=agent_port,
            telegram_bot_token=telegram_token,
            telegram_allowed_chat_ids=telegram_chat_ids,
            embedding_model=embedding_model,
            memory_db_path=memory_db_path,
            soul_path=soul_path,
            shell_command_timeout=shell_command_timeout,
            shell_max_output=shell_max_output,
            context_max_tokens=context_max_tokens,
            context_preserve_recent=context_preserve_recent,
            codex_timeout=codex_timeout,
            codex_max_output=codex_max_output,
            github_token=github_token,
            history_path=history_path,
            whisper_model=whisper_model,
            max_tool_rounds=max_tool_rounds,
            daemon_pid_path=daemon_pid_path,
            daemon_log_path=daemon_log_path,
            scheduler_db_path=scheduler_db_path,
            scheduler_poll_interval=scheduler_poll_interval,
            scheduler_tasks=scheduler_tasks,
            repos_db_path=repos_db_path,
        )
