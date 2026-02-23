"""Tool registry for managing and dispatching agent tools."""

from typing import Any

from src.tools.base import Tool


class ToolRegistry:
    """Registry that stores tools and dispatches calls by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI-formatted tool schemas for all registered tools."""
        return [tool.schema for tool in self._tools.values()]

    def execute(self, tool_name: str, **kwargs: Any) -> str:
        """Dispatch a tool call by name.

        Raises:
            KeyError: If tool_name is not registered.
        """
        if tool_name not in self._tools:
            raise KeyError(f"Unknown tool: '{tool_name}'")
        return self._tools[tool_name].execute(**kwargs)

    @property
    def tool_names(self) -> list[str]:
        """List of registered tool names."""
        return list(self._tools.keys())
