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


@pytest.mark.unit
def test_usage_llm_edge_label_uses_backend_class_and_model() -> None:
    """Usage LLM edge labels name the inner backend class and configured model."""
    from agentflow.llm.LlmConfig import LlmConfig
    from agentflow.llm.LlmConnector import LlmConnector

    connector = LlmConnector(
        config=LlmConfig(backend="openai", model="gpt-4o-mini", api_key="test"),
    )
    label = AgentApp._usage_llm_edge_label("DeviceWorkerVertex", connector)
    assert label == "DeviceWorkerVertex-OpenAiConnector-gpt-4o-mini"


@pytest.mark.unit
def test_usage_llm_edge_label_for_anthropic_backend() -> None:
    """Anthropic backends appear as AnthropicConnector in usage edge labels."""
    from agentflow.llm.LlmConfig import LlmConfig
    from agentflow.llm.LlmConnector import LlmConnector

    connector = LlmConnector(
        config=LlmConfig(backend="anthropic", model="claude-3-5-sonnet", api_key="test"),
    )
    label = AgentApp._usage_llm_edge_label("SafetyJudgeVertex", connector)
    assert label == "SafetyJudgeVertex-AnthropicConnector-claude-3-5-sonnet"


@pytest.mark.unit
def test_usage_tools_edge_label_format() -> None:
    """Usage tool-registry edge labels follow '<Vertex>-Tools: <key>'."""
    label = AgentApp._usage_tools_edge_label("DeviceWorkerVertex", "default")
    assert label == "DeviceWorkerVertex-Tools: default"


@pytest.mark.unit
def test_llm_connector_base_exposes_backend_and_model_in_description() -> None:
    """All real connectors expose backend and model in description dicts."""
    from agentflow.llm.LlmConfig import LlmConfig
    from agentflow.llm.LlmConnector import LlmConnector
    from agentflow.llm.connectors.AnthropicConnector import AnthropicConnector
    from agentflow.llm.connectors.OpenAiConnector import OpenAiConnector

    openai_cfg = LlmConfig(backend="openai", model="gpt-4o", api_key="test")
    anthropic_cfg = LlmConfig(backend="anthropic", model="claude-3-5-sonnet", api_key="test")

    for connector in (
        LlmConnector(config=openai_cfg),
        OpenAiConnector(openai_cfg),
        AnthropicConnector(anthropic_cfg),
    ):
        desc = connector.get_description_item_dict()
        assert desc["backend"] == connector.config.backend
        assert desc["model"] == connector.config.model
