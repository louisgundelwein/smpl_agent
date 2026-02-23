"""Abstract base class for all tools."""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Base class for agent tools.

    Subclasses must implement name, schema, and execute.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name. Must match the 'name' in the schema."""
        ...

    @property
    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """OpenAI tool schema in Chat Completions format.

        Returns a dict like:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": { ... }
            }
        }
        """
        ...

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result for the LLM."""
        ...
