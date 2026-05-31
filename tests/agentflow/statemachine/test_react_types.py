"""Tests for ReActState, ReActPatch, ReActSignal, and Signal alias (T103-01)."""
from __future__ import annotations

import dataclasses
import operator
from enum import Enum, auto
from typing import get_type_hints

import pytest

from agentflow.statemachine import (
    ReActPatch,
    ReActSignal,
    ReActState,
    Signal,
)

# ---------------------------------------------------------------------------
# ReActState
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReActState:
    def test_react_state_is_frozen_dataclass(self) -> None:
        """ReActState must be immutable — assigning any field must raise."""
        state = ReActState()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            state.step = 1  # type: ignore[misc]

    def test_react_state_default_messages_is_empty(self) -> None:
        """Default messages must be an empty tuple."""
        state = ReActState()
        assert state.messages == ()

    def test_react_state_messages_annotation_has_operator_add(self) -> None:
        """The messages field annotation must carry operator.add as its merge strategy."""
        hints = get_type_hints(ReActState, include_extras=True)
        msg_hint = hints["messages"]
        # Annotated[tuple[dict, ...], operator.add] — metadata contains operator.add
        metadata = getattr(msg_hint, "__metadata__", ())
        assert operator.add in metadata, (
            f"Expected operator.add in Annotated metadata for 'messages', got {metadata}"
        )

    def test_react_state_constructs_with_messages(self) -> None:
        """ReActState accepts a tuple of messages and exposes them via .messages."""
        msgs = ({"role": "user", "content": "hello"},)
        state = ReActState(messages=msgs)
        assert state.messages == msgs

    def test_react_state_default_final_answer_is_empty_string(self) -> None:
        state = ReActState()
        assert state.final_answer == ""

    def test_react_state_default_step_is_zero(self) -> None:
        state = ReActState()
        assert state.step == 0


# ---------------------------------------------------------------------------
# ReActPatch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReActPatch:
    def test_react_patch_is_frozen_dataclass(self) -> None:
        """ReActPatch must also be immutable."""
        patch = ReActPatch()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            patch.final_answer = "x"  # type: ignore[misc]

    def test_react_patch_default_messages_is_empty(self) -> None:
        patch = ReActPatch()
        assert patch.messages == ()


# ---------------------------------------------------------------------------
# ReActSignal
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReActSignal:
    def test_react_signal_tool_call_is_enum_member(self) -> None:
        """ReActSignal.tool_call must exist and be an Enum member."""
        assert hasattr(ReActSignal, "tool_call")
        assert isinstance(ReActSignal.tool_call, Enum)

    def test_react_signal_final_answer_is_enum_member(self) -> None:
        assert isinstance(ReActSignal.final_answer, Enum)

    def test_react_signal_max_steps_is_enum_member(self) -> None:
        assert isinstance(ReActSignal.max_steps, Enum)

    def test_react_signal_members_are_distinct(self) -> None:
        """All three signals must be different values."""
        assert ReActSignal.tool_call is not ReActSignal.final_answer
        assert ReActSignal.tool_call is not ReActSignal.max_steps
        assert ReActSignal.final_answer is not ReActSignal.max_steps


# ---------------------------------------------------------------------------
# Signal alias
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSignalAlias:
    def test_signal_is_enum(self) -> None:
        """Signal must be the Enum base class so user signal sets can subclass it."""
        assert Signal is Enum

    def test_custom_enum_can_subclass_signal(self) -> None:
        """Subclassing Signal with auto() members must work exactly like subclassing Enum."""

        class Foo(Signal):
            bar = auto()
            baz = auto()

        assert isinstance(Foo.bar, Enum)
        assert isinstance(Foo.baz, Enum)
        assert Foo.bar is not Foo.baz
