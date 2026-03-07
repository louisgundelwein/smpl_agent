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
    openai_timeout: int
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
    max_message_content: int
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
    reddit_enabled: bool
    reddit_action_delay: int
    browser_profiles_dir: str
    browser_use_api_key: str | None
    instagram_enabled: bool
    instagram_action_delay: int
    image_gen_base_url: str | None
    image_gen_api_key: str | None
    browser_stealth_mode: str
    browser_stealth_timezone: str
    linkedin_manual_login_timeout: int
    encryption_key_path: str

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.openai_timeout <= 0:
            raise ValueError("OPENAI_TIMEOUT must be > 0")
        if self.shell_command_timeout <= 0:
            raise ValueError("SHELL_COMMAND_TIMEOUT must be > 0")
        if self.context_max_tokens <= 0:
            raise ValueError("CONTEXT_MAX_TOKENS must be > 0")
        if self.max_message_content <= 0:
            raise ValueError("MAX_MESSAGE_CONTENT must be > 0")
        if self.codex_timeout <= 0:
            raise ValueError("CODEX_TIMEOUT must be > 0")
        if self.max_tool_rounds <= 0:
            raise ValueError("MAX_TOOL_ROUNDS must be > 0")
        if self.max_continuations < 0:
            raise ValueError("AGENT_MAX_CONTINUATIONS must be >= 0")
        if self.scheduler_poll_interval <= 0:
            raise ValueError("SCHEDULER_POLL_INTERVAL must be > 0")
        if self.max_subagents <= 0:
            raise ValueError("MAX_SUBAGENTS must be > 0")
        if self.subagent_tool_rounds <= 0:
            raise ValueError("SUBAGENT_TOOL_ROUNDS must be > 0")
        if self.browser_use_timeout <= 0:
            raise ValueError("BROWSER_USE_TIMEOUT must be > 0")
        if self.auto_memory_extract_interval <= 0:
            raise ValueError("AUTO_MEMORY_EXTRACT_INTERVAL must be > 0")
        if self.auto_recall_threshold < 0 or self.auto_recall_threshold > 1:
            raise ValueError("AUTO_RECALL_THRESHOLD must be between 0 and 1")
        if self.auto_recall_top_k <= 0:
            raise ValueError("AUTO_RECALL_TOP_K must be > 0")
        if self.temp_file_ttl_hours <= 0:
            raise ValueError("TEMP_FILE_TTL_HOURS must be > 0")
        if self.embedding_dimensions <= 0:
            raise ValueError("EMBEDDING_DIMENSIONS must be > 0")

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
        openai_timeout = int(os.getenv("OPENAI_TIMEOUT", "120"))
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
        max_message_content = int(os.getenv("MAX_MESSAGE_CONTENT", "30000"))
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
        reddit_enabled = os.getenv("REDDIT_ENABLED", "false").lower() in ("true", "1", "yes")
        reddit_action_delay = int(os.getenv("REDDIT_ACTION_DELAY_SECONDS", "3"))
        browser_profiles_dir = os.getenv("BROWSER_PROFILES_DIR", "browser_profiles")
        browser_use_api_key = os.getenv("BROWSER_USE_API_KEY")
        instagram_enabled = os.getenv("INSTAGRAM_ENABLED", "false").lower() in ("true", "1", "yes")
        instagram_action_delay = int(os.getenv("INSTAGRAM_ACTION_DELAY_SECONDS", "5"))
        image_gen_base_url = os.getenv("IMAGE_GEN_BASE_URL") or None
        image_gen_api_key = os.getenv("IMAGE_GEN_API_KEY") or None
        browser_stealth_mode = os.getenv("BROWSER_STEALTH_MODE", "default")
        browser_stealth_timezone = os.getenv("BROWSER_STEALTH_TIMEZONE", "Europe/Berlin")
        linkedin_manual_login_timeout = int(os.getenv("LINKEDIN_MANUAL_LOGIN_TIMEOUT", "300"))
        encryption_key_path = os.getenv("ENCRYPTION_KEY_PATH", "encryption.key")

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
            openai_timeout=openai_timeout,
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
            max_message_content=max_message_content,
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
            reddit_enabled=reddit_enabled,
            reddit_action_delay=reddit_action_delay,
            browser_profiles_dir=browser_profiles_dir,
            browser_use_api_key=browser_use_api_key,
            instagram_enabled=instagram_enabled,
            instagram_action_delay=instagram_action_delay,
            image_gen_base_url=image_gen_base_url,
            image_gen_api_key=image_gen_api_key,
            browser_stealth_mode=browser_stealth_mode,
            browser_stealth_timezone=browser_stealth_timezone,
            linkedin_manual_login_timeout=linkedin_manual_login_timeout,
            encryption_key_path=encryption_key_path,
        )
