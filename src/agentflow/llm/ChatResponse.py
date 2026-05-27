"""Value objects representing a single LLM chat completion response.

Decouples all layers above LlmConnector from the openai SDK types so the SDK
can be swapped without touching anything that processes responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UsageInfo:
    """Token usage reported by the LLM backend for a single completion call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def __str__(self) -> str:
        return (
            f"prompt={self.prompt_tokens} "
            f"completion={self.completion_tokens} "
            f"total={self.total_tokens}"
        )


@dataclass
class ToolCallFunction:
    """Function descriptor inside a tool call — name, raw JSON arguments, backend extras.

    The ``extra`` field preserves backend-specific fields (e.g. Gemini's
    ``thought_signature``) that must be echoed back verbatim in the next turn.
    """

    name: str
    arguments: str  # raw JSON string as returned by the LLM
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallInfo:
    """Single tool call issued by the LLM in one completion response."""

    id: str
    function: ToolCallFunction
    type: str = "function"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Convenience accessor for the function name."""
        return self.function.name

    @property
    def arguments(self) -> str:
        """Convenience accessor for the raw JSON arguments string."""
        return self.function.arguments


@dataclass
class ChatResponse:
    """Normalised response from a single LLM chat completion call.

    Designed to be immutable after construction. Use ``to_message_dict()`` to
    append the response to a conversation history list.
    """

    role: str
    content: str | None
    tool_calls: list[ToolCallInfo] | None
    usage: UsageInfo | None

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def has_tool_calls(self) -> bool:
        """True when the LLM requested one or more tool calls."""
        return bool(self.tool_calls)

    @property
    def text(self) -> str:
        """Content as a plain string; empty string when the model returned no text."""
        return self.content or ""

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_message_dict(self) -> dict[str, Any]:
        """Serialise to an OpenAI-compatible message dict for appending to history.

        Returns:
            Dict suitable for passing back in the ``messages`` list of the next call.
            Includes ``tool_calls`` key only when present, preserving backend extras.
        """
        msg: dict[str, Any] = {"role": self.role}
        if self.content:
            msg["content"] = self.content
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                        **tc.function.extra,
                    },
                    **tc.extra,
                }
                for tc in self.tool_calls
            ]
        return msg

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        parts: list[str] = [f"role={self.role!r}"]
        if self.content:
            preview = self.content[:60].replace("\n", " ")
            suffix = "..." if len(self.content) > 60 else ""
            parts.append(f"content={preview!r}{suffix}")
        if self.tool_calls:
            names = [tc.name for tc in self.tool_calls]
            parts.append(f"tool_calls={names}")
        if self.usage:
            parts.append(f"usage=[{self.usage}]")
        return f"ChatResponse({', '.join(parts)})"
