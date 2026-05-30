"""Unit tests for EnumSignal and StdSignal."""

from __future__ import annotations

from enum import Enum, auto

import pytest

from agentflow.statemachine import EnumSignal, StdSignal


@pytest.mark.unit
class TestStdSignal:
    def test_std_signal_has_ok_fail_done_members(self) -> None:
        assert StdSignal.ok.name == "ok"
        assert StdSignal.fail.name == "fail"
        assert StdSignal.done.name == "done"

    def test_std_signal_member_is_enum_instance(self) -> None:
        # EnumSignal is a TypeAlias for Enum; runtime check uses Enum.
        assert isinstance(StdSignal.ok, Enum)

    def test_custom_signal_can_be_defined_independently(self) -> None:
        class CustomSignal(EnumSignal):
            approved = auto()
            rejected = auto()

        assert isinstance(CustomSignal.approved, Enum)
        assert CustomSignal.approved.name == "approved"
