"""Registry that holds ToolBase instances and dispatches LLM tool calls.

ToolRegistry is the bridge between the agentic loop and the concrete tool
objects.  It is responsible for:
  - Registering tool instances (which may carry state).
  - Producing the OpenAI-compatible schema list passed to ``LlmConnector.chat()``.
  - Dispatching a tool call by name with JSON-encoded arguments.
  - Returning the string result to be inserted as a ``tool`` role message.

Pattern: Registry (PEAA).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from git_root_to_syspath import agr
agr()

from src.agentflow.describable.describable import Describable
from src.agentflow.tools.Tool import ToolBase

logger = logging.getLogger(__name__)


class ToolRegistry(Describable):
    """Registry of stateful tool objects with schema generation and call dispatch.

    Usage::

        registry = ToolRegistry(tools=[GetWeather(api_key="..."), Calculator()])

        # Pass schemas to the LLM:
        response = connector.chat(messages, tools=registry.schemas())

        # Dispatch each tool call returned by the LLM:
        for call in response.tool_calls:
            result = registry.execute(call.name, call.arguments)

    Pattern: Registry (PEAA).
    """

    def __init__(self, tools: list[ToolBase] | None = None) -> None:
        super().__init__()
        self._tools: dict[str, ToolBase] = {}
        self.tools: list[ToolBase] = []  # public list kept in sync; used by Describable graph
        for tool in tools or []:
            self.register(tool)

    def _get_own_attributes(self) -> dict[str, Any]:
        d = super()._get_own_attributes()
        d["tool_count"] = len(self._tools)
        d["tool_names"] = self.names()
        return d

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: ToolBase) -> None:
        """Register a tool instance.

        Args:
            tool: ``ToolBase`` instance to register.  The instance's
                  ``name`` property is used as the registry key.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ValueError(
                f"Tool {tool.name!r} is already registered. "
                "Unregister it first or use a subclass with a different name."
            )
        self._tools[tool.name] = tool
        self.tools.append(tool)
        logger.debug("Tool registered: name=%s type=%s", tool.name, type(tool).__name__)

    def unregister(self, name: str) -> None:
        """Remove a previously registered tool by name.

        Args:
            name: Tool name to remove.

        Raises:
            KeyError: If no tool with the given name is registered.
        """
        if name not in self._tools:
            raise KeyError(f"No tool named {name!r} is registered.")
        tool = self._tools.pop(name)
        self.tools.remove(tool)
        logger.debug("Tool unregistered: name=%s", name)

    # ------------------------------------------------------------------
    # Schema generation
    # ------------------------------------------------------------------

    def schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool definition list for all registered tools.

        Returns:
            List of dicts suitable for passing as the ``tools`` argument to
            ``LlmConnector.chat()``.
        """
        return [tool.to_openai_schema() for tool in self._tools.values()]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def execute(self, name: str, arguments_json: str) -> str:
        """Execute a registered tool by name with JSON-encoded arguments.

        Parses ``arguments_json``, calls ``tool.execute(**args)``, and
        serialises the result to a string suitable for the ``tool`` role
        message content.

        Args:
            name: Tool name as returned by the LLM.
            arguments_json: Raw JSON string of keyword arguments from the LLM.
                            An empty or whitespace-only string is treated as
                            ``{}`` (no arguments).

        Returns:
            String result to feed back as the tool message content.

        Raises:
            KeyError: If no tool with the given name is registered.
        """
        if name not in self._tools:
            raise KeyError(
                f"Unknown tool: {name!r}. Registered: {sorted(self._tools)}"
            )

        try:
            args: dict[str, Any] = (
                json.loads(arguments_json) if arguments_json.strip() else {}
            )
        except json.JSONDecodeError as exc:
            logger.warning(
                "Tool argument parse error: tool=%s error=%s raw=%r",
                name,
                exc,
                arguments_json[:200],
            )
            args = {}

        tool = self._tools[name]
        logger.debug("Executing tool: name=%s args=%s", name, args)

        try:
            result = tool.execute(**args)
        except Exception as exc:
            logger.error(
                "Tool execution error: name=%s args=%s error=%s",
                name,
                args,
                exc,
            )
            raise

        result_str = str(result)
        logger.debug("Tool result: name=%s result=%r", name, result_str[:200])
        return result_str

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get(self, name: str) -> ToolBase | None:
        """Return a registered tool by name, or ``None`` if not found.

        Args:
            name: Tool name.

        Returns:
            The ``ToolBase`` instance, or ``None``.
        """
        return self._tools.get(name)

    def names(self) -> list[str]:
        """Return a sorted list of registered tool names.

        Returns:
            Sorted list of name strings.
        """
        return sorted(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={self.names()})"
