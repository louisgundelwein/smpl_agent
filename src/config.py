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
    embedding_dimensions: int
    database_url: str
    soul_path: str
    shell_command_timeout: int
    shell_max_output: int
    context_max_tokens: int
    context_preserve_recent: int
    codex_timeout: int
    codex_max_output: int
    github_token: str | None
    whisper_model: str
    max_tool_rounds: int
    max_continuations: int
    daemon_pid_path: str
    daemon_log_path: str
    scheduler_poll_interval: int
    scheduler_tasks: str
    max_subagents: int
    subagent_tool_rounds: int
    auto_memory: bool
    auto_memory_extract_interval: int
    auto_recall_threshold: float
    auto_recall_top_k: int
    browser_use_enabled: bool
    browser_use_timeout: int
    browser_use_recording_dir: str
    temp_file_ttl_hours: int
    marketing_enabled: bool
    linkedin_enabled: bool
    linkedin_action_delay: int
    linkedin_knowledge_dir: str

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
        telegram_chat_ids = []
        for x in raw_ids.split(","):
            x = x.strip()
            if x:
                try:
                    telegram_chat_ids.append(int(x))
                except ValueError:
                    raise ValueError(
                        f"Invalid TELEGRAM_ALLOWED_CHAT_IDS entry: '{x}' (must be integer)"
                    )

        embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
        embedding_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
        database_url = os.getenv("DATABASE_URL", "")
        soul_path = os.getenv("SOUL_PATH", "SOUL.md")
        shell_command_timeout = int(os.getenv("SHELL_COMMAND_TIMEOUT", "30"))
        shell_max_output = int(os.getenv("SHELL_MAX_OUTPUT", "50000"))
        context_max_tokens = int(os.getenv("CONTEXT_MAX_TOKENS", "100000"))
        context_preserve_recent = int(os.getenv("CONTEXT_PRESERVE_RECENT", "10"))
        codex_timeout = int(os.getenv("CODEX_TIMEOUT", "300"))
        codex_max_output = int(os.getenv("CODEX_MAX_OUTPUT", "50000"))
        github_token = os.getenv("GITHUB_TOKEN") or None
        whisper_model = os.getenv("WHISPER_MODEL", "openai/whisper-large-v3-turbo")
        max_tool_rounds = int(os.getenv("MAX_TOOL_ROUNDS", "25"))
        max_continuations = int(os.getenv("AGENT_MAX_CONTINUATIONS", "20"))
        daemon_pid_path = os.getenv("DAEMON_PID_PATH", "agent.pid")
        daemon_log_path = os.getenv("DAEMON_LOG_PATH", "agent.log")
        scheduler_poll_interval = int(os.getenv("SCHEDULER_POLL_INTERVAL", "30"))
        scheduler_tasks = os.getenv("SCHEDULER_TASKS", "")
        max_subagents = int(os.getenv("MAX_SUBAGENTS", "10"))
        subagent_tool_rounds = int(os.getenv("SUBAGENT_TOOL_ROUNDS", "15"))
        auto_memory = os.getenv("AUTO_MEMORY", "true").lower() in ("true", "1", "yes")
        auto_memory_extract_interval = int(os.getenv("AUTO_MEMORY_EXTRACT_INTERVAL", "3"))
        auto_recall_threshold = float(os.getenv("AUTO_RECALL_THRESHOLD", "0.55"))
        auto_recall_top_k = int(os.getenv("AUTO_RECALL_TOP_K", "5"))
        browser_use_enabled = os.getenv("BROWSER_USE_ENABLED", "false").lower() in ("true", "1", "yes")
        browser_use_timeout = int(os.getenv("BROWSER_USE_TIMEOUT", "300"))
        browser_use_recording_dir = os.getenv("BROWSER_USE_RECORDING_DIR", "browser_recordings")
        temp_file_ttl_hours = int(os.getenv("TEMP_FILE_TTL_HOURS", "72"))
        marketing_enabled = os.getenv("MARKETING_ENABLED", "false").lower() in ("true", "1", "yes")
        linkedin_enabled = os.getenv("LINKEDIN_ENABLED", "false").lower() in ("true", "1", "yes")
        linkedin_action_delay = int(os.getenv("LINKEDIN_ACTION_DELAY_SECONDS", "2"))
        linkedin_knowledge_dir = os.getenv("LINKEDIN_KNOWLEDGE_DIR", "src/marketing/platform_guides")

        if not openai_key:
            raise ValueError("OPENAI_API_KEY is required")
        if not brave_key:
            raise ValueError("BRAVE_SEARCH_API_KEY is required")
        if not database_url:
            raise ValueError("DATABASE_URL is required")

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
            embedding_dimensions=embedding_dimensions,
            database_url=database_url,
            soul_path=soul_path,
            shell_command_timeout=shell_command_timeout,
            shell_max_output=shell_max_output,
            context_max_tokens=context_max_tokens,
            context_preserve_recent=context_preserve_recent,
            codex_timeout=codex_timeout,
            codex_max_output=codex_max_output,
            github_token=github_token,
            whisper_model=whisper_model,
            max_tool_rounds=max_tool_rounds,
            max_continuations=max_continuations,
            daemon_pid_path=daemon_pid_path,
            daemon_log_path=daemon_log_path,
            scheduler_poll_interval=scheduler_poll_interval,
            scheduler_tasks=scheduler_tasks,
            max_subagents=max_subagents,
            subagent_tool_rounds=subagent_tool_rounds,
            auto_memory=auto_memory,
            auto_memory_extract_interval=auto_memory_extract_interval,
            auto_recall_threshold=auto_recall_threshold,
            auto_recall_top_k=auto_recall_top_k,
            browser_use_enabled=browser_use_enabled,
            browser_use_timeout=browser_use_timeout,
            browser_use_recording_dir=browser_use_recording_dir,
            temp_file_ttl_hours=temp_file_ttl_hours,
            marketing_enabled=marketing_enabled,
            linkedin_enabled=linkedin_enabled,
            linkedin_action_delay=linkedin_action_delay,
            linkedin_knowledge_dir=linkedin_knowledge_dir,
        )
