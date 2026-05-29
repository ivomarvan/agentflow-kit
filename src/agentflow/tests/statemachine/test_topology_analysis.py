"""Unit tests for StateGraph._analyze_asymmetric_joins static analysis."""

from __future__ import annotations

import enum
import logging
from typing import Any

import pytest

from src.agentflow.statemachine.context import Context
from src.agentflow.statemachine.topology import Parallel, StateGraph, Transition
from src.agentflow.statemachine.vertex import StateVertex


class _Sig(enum.Enum):
    ok = "ok"


class NodeA(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class NodeB(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class NodeC(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class NodeD(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


class NodeE(StateVertex):
    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return (object(), object())


@pytest.mark.unit
def test_symmetric_join_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Graph A → Parallel(B, C) → D: both branches depth 1 from A — no WARNING.

    BFS distances from A: B=1, C=1. Predecessors of D are {B, C} with equal
    depths — no asymmetry, so _analyze_asymmetric_joins must not emit WARNING.
    """
    with caplog.at_level(logging.WARNING):
        StateGraph(
            start=NodeA,
            transitions=[
                Transition(NodeA, _Sig.ok, Parallel(NodeB, NodeC)),
                Transition(NodeB, _Sig.ok, NodeD),
                Transition(NodeC, _Sig.ok, NodeD),
            ],
        )
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


@pytest.mark.unit
def test_asymmetric_join_emits_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Graph A→Parallel(B,C), B→D, C→E→D: branch depths differ — WARNING emitted.

    BFS distances from A: B=1, C=1, E=2. Predecessors of D are {B, E} with
    depths {1, 2} — asymmetric join. WARNING must be emitted and contain 'NodeD'.
    """
    with caplog.at_level(logging.WARNING):
        StateGraph(
            start=NodeA,
            transitions=[
                Transition(NodeA, _Sig.ok, Parallel(NodeB, NodeC)),
                Transition(NodeB, _Sig.ok, NodeD),
                Transition(NodeC, _Sig.ok, NodeE),
                Transition(NodeE, _Sig.ok, NodeD),
            ],
        )
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) >= 1, "Expected at least one WARNING for asymmetric join"
    assert any("NodeD" in r.getMessage() for r in warnings), (
        "WARNING must mention the join node name 'NodeD'"
    )


@pytest.mark.unit
def test_single_incoming_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Linear A → B → C: no multi-in nodes — no WARNING emitted.

    Every node has at most one predecessor so _analyze_asymmetric_joins finds
    no join candidates and must produce zero WARNING log records.
    """
    with caplog.at_level(logging.WARNING):
        StateGraph(
            start=NodeA,
            transitions=[
                Transition(NodeA, _Sig.ok, NodeB),
                Transition(NodeB, _Sig.ok, NodeC),
            ],
        )
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)
