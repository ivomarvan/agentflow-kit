"""Unit tests for apply_patches and per-field reducer dispatch."""

from __future__ import annotations

import logging
import operator
from dataclasses import dataclass
from typing import Annotated

import pytest

from src.agentflow.statemachine import UNSET, apply_patches


@dataclass(frozen=True)
class MyState:
    messages: Annotated[tuple[str, ...], operator.add] = ()
    score: Annotated[float, max] = 0.0
    author: str = ""


@dataclass
class MyPatch:
    messages: tuple[str, ...] | None = None
    score: float | None = None
    author: str | None = None


@pytest.mark.unit
class TestApplyPatches:
    def test_apply_patches_uses_reducer_for_annotated_field(self) -> None:
        """operator.add on tuple concatenates contributions from two patches."""
        state = MyState()
        patch1 = MyPatch(messages=("hello",))
        patch2 = MyPatch(messages=("world",))
        result = apply_patches(state, [patch1, patch2])
        assert result.messages == ("hello", "world")

    def test_apply_patches_max_reducer_keeps_higher_score(self) -> None:
        """max reducer selects the highest value written across patches."""
        state = MyState(score=1.0)
        patch1 = MyPatch(score=5.0)
        patch2 = MyPatch(score=3.0)
        result = apply_patches(state, [patch1, patch2])
        assert result.score == 5.0

    def test_apply_patches_no_reducer_last_writer_wins(self) -> None:
        """Field without a reducer keeps the value from the last contributing patch."""
        state = MyState(author="original")
        patch1 = MyPatch(author="first")
        patch2 = MyPatch(author="last")
        result = apply_patches(state, [patch1, patch2])
        assert result.author == "last"

    def test_apply_patches_no_reducer_warns_on_collision(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """caplog captures WARNING when two patches write different values without reducer."""
        state = MyState()
        patch1 = MyPatch(author="Alice")
        patch2 = MyPatch(author="Bob")
        with caplog.at_level(logging.WARNING):
            apply_patches(state, [patch1, patch2])
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_apply_patches_skips_none_value_in_patch(self) -> None:
        """None and UNSET in patch fields leave the corresponding state fields unchanged."""
        import types

        state = MyState(author="original", score=9.0)
        none_patch = MyPatch(author=None, score=None)
        # UNSET sentinel must also be treated as "do not set"
        unset_patch = types.SimpleNamespace(messages=UNSET, score=UNSET, author=UNSET)
        result = apply_patches(state, [none_patch, unset_patch])
        assert result is state

    def test_apply_patches_returns_new_instance(self) -> None:
        """Applying a patch with actual values produces a distinct object; original unchanged."""
        state = MyState(author="original")
        patch = MyPatch(author="updated")
        result = apply_patches(state, [patch])
        assert result is not state
        assert result.author == "updated"
        assert state.author == "original"

    def test_apply_patches_empty_patch_list_returns_same_state(self) -> None:
        """Empty patch list returns the identical state object (no copy)."""
        state = MyState(author="unchanged")
        result = apply_patches(state, [])
        assert result is state
