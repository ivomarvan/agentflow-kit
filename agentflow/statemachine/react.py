"""Library-provided types for the standard ReAct (Reason+Act) agent pattern.

Using these eliminates per-application boilerplate for the common LLM+tool loop.
Import from agentflow.statemachine.
"""

import operator
from dataclasses import dataclass, field
from enum import auto
from typing import Annotated

from agentflow.statemachine.signal import EnumSignal


@dataclass(frozen=True)
class ToolCallInfo:
    """Minimal info about a single tool call returned by the LLM.

    Attributes match the wire format so callers can reconstruct the
    tool-result message without additional parsing.
    """

    id: str
    name: str
    arguments: str  # raw JSON string


@dataclass(frozen=True)
class ReActState:
    """Standard immutable state for ReAct-pattern agents.

    The ``messages`` field uses ``operator.add`` as its merge strategy so
    that successive patches append rather than replace the conversation history.
    """

    messages: Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    last_tool_calls: tuple[ToolCallInfo, ...] = field(default_factory=tuple)
    final_answer: str = ""
    step: int = 0


@dataclass(frozen=True)
class ReActPatch:
    """Partial state update emitted by ReAct vertices; merged by the runner."""

    messages: tuple[dict, ...] = field(default_factory=tuple)
    last_tool_calls: tuple[ToolCallInfo, ...] = field(default_factory=tuple)
    final_answer: str = ""
    step: int = 0


class ReActSignal(EnumSignal):
    """Standard signals for the ReAct pattern."""

    tool_call = auto()
    final_answer = auto()
    max_steps = auto()
