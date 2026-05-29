"""Unit tests for VertexResolver."""
from __future__ import annotations

from typing import Any

import pytest

from src.agentflow.statemachine.context import Context
from src.agentflow.statemachine.resolver import VertexResolver
from src.agentflow.statemachine.signal import StdSignal
from src.agentflow.statemachine.vertex import StateVertex


class _SimpleVertex(StateVertex):
    """Minimal concrete StateVertex with no-arg constructor for resolver tests."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return StdSignal.done, None


class _ParamVertex(StateVertex):
    """StateVertex subclass that requires a constructor argument without a default."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return StdSignal.done, None


@pytest.mark.unit
def test_resolve_instance_returned_unchanged() -> None:
    """resolve() with an already-instantiated vertex returns the same object."""
    resolver = VertexResolver()
    instance = _SimpleVertex()
    result = resolver.resolve(instance)
    assert result is instance


@pytest.mark.unit
def test_resolve_class_creates_instance() -> None:
    """resolve() with a class returns an instance of that class."""
    resolver = VertexResolver()
    result = resolver.resolve(_SimpleVertex)
    assert isinstance(result, _SimpleVertex)


@pytest.mark.unit
def test_resolve_class_is_singleton() -> None:
    """resolve() called twice for the same class returns id()-identical object."""
    resolver = VertexResolver()
    first = resolver.resolve(_SimpleVertex)
    second = resolver.resolve(_SimpleVertex)
    assert id(first) == id(second)


@pytest.mark.unit
def test_resolve_class_without_default_raises() -> None:
    """resolve() with a class whose __init__ has required params raises ValueError."""
    resolver = VertexResolver()
    with pytest.raises(ValueError, match="Cannot auto-instantiate"):
        resolver.resolve(_ParamVertex)


@pytest.mark.unit
def test_clear_resets_cache() -> None:
    """After clear(), the next resolve() creates a fresh instance (different id)."""
    resolver = VertexResolver()
    first = resolver.resolve(_SimpleVertex)
    resolver.clear()
    second = resolver.resolve(_SimpleVertex)
    assert id(first) != id(second)
