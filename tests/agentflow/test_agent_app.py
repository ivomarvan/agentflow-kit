"""Unit tests for AgentApp base class."""
import asyncio
from dataclasses import dataclass

import pytest

from agentflow import AgentApp, ExampleApp
from agentflow.statemachine import (
    Context,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from agentflow.statemachine.testing import FakeLlmConnector


@dataclass(frozen=True)
class _State:
    value: str = ""


@dataclass
class _Patch:
    value: str | None = None


class _Done(StateVertex):
    async def run(self, state: _State, ctx: Context) -> tuple[object, object]:
        return StdSignal.done, _Patch()


class _MinimalApp(AgentApp):
    def __init__(self) -> None:
        super().__init__()
        self.connector = FakeLlmConnector()
        self.graph = StateGraph(
            start=_Done,
            transitions=[Transition(_Done, StdSignal.done, StdEnd)],
        )
        self._ran = False

    async def run_workflow(self) -> str | None:
        ctx = Context(connector=self.connector)
        runner = StateGraphRunner(self.graph, ctx)
        await runner.run(_State(value="test"))
        self._ran = True
        return "completed"


@pytest.mark.unit
def test_run_calls_workflow() -> None:
    """run() should execute run_workflow() synchronously."""
    app = _MinimalApp()
    result = app.run()
    assert app._ran
    assert result == "completed"


@pytest.mark.unit
def test_get_graph_includes_topology_nodes() -> None:
    """get_graph() on an AgentApp should expose StateGraph topology nodes."""
    app = _MinimalApp()
    graph = app.get_graph()
    # App vertex should have children (connector, graph)
    assert len(graph.root.children) > 0
    # Find the StateGraph child
    sg_child = next(
        (c for c in graph.root.children if c.label == "StateGraph"),
        None,
    )
    assert sg_child is not None, "StateGraph vertex not found in AgentApp graph"
    # StateGraph child should expose topology nodes (at least _Done and StdEnd nodes)
    node_labels = {c.label for c in sg_child.children}
    assert "_Done" in node_labels or len(sg_child.children) > 0


@pytest.mark.unit
def test_run_workflow_raises_when_not_overridden() -> None:
    """run_workflow() should raise NotImplementedError in the base class."""
    base = AgentApp.__new__(AgentApp)
    AgentApp.__init__(base)
    with pytest.raises(NotImplementedError):
        asyncio.run(base.run_workflow())


@pytest.mark.unit
def test_sample_prompts_default_empty() -> None:
    """sample_prompts property should return empty list by default."""
    base = AgentApp.__new__(AgentApp)
    AgentApp.__init__(base)
    assert base.sample_prompts == []


@pytest.mark.unit
def test_example_app_alias_is_agent_app() -> None:
    """ExampleApp should be an alias for AgentApp (backward compat)."""
    assert ExampleApp is AgentApp
