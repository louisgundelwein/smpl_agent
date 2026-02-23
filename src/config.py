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

        if not openai_key:
            raise ValueError("OPENAI_API_KEY is required")
        if not brave_key:
            raise ValueError("BRAVE_SEARCH_API_KEY is required")

        return cls(
            openai_api_key=openai_key,
            openai_model=model,
            openai_base_url=base_url,
            brave_search_api_key=brave_key,
        )
