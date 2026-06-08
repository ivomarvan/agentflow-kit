"""Regression tests for E106 model-first vertices (Inspector + graph)."""
from __future__ import annotations

from typing import Any

import pytest

from agentflow import AgentApp
from agentflow.llm.connectors import LlmConnector
from agentflow.statemachine import Context, StateGraph, StateVertex, StdEnd, StdSignal, Transition


class _ModelFirstVertex(StateVertex):
    """Vertex using inherited model field instead of connector key."""

    model: str = "gpt-4o-mini"

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        return StdSignal.done, object()


def _model_first_app() -> AgentApp:
    vertex = _ModelFirstVertex()
    end = StdEnd()
    return AgentApp(
        context=Context(
            llm_connectors={
                "economy": LlmConnector(model="gpt-4o-mini"),
                "quality": LlmConnector(model="gemini-3.5-flash"),
            },
        ),
        state_graph=StateGraph(
            start=vertex,
            transitions=[Transition(vertex, StdSignal.done, end)],
        ),
    )


@pytest.mark.unit
def test_config_schema_hides_context_llm_connector_groups() -> None:
    """get_config_schema() must not expose economy/quality connector groups."""
    schema = _model_first_app().get_config_schema()
    props = schema.get("properties", {})
    assert "economy" not in props
    assert "quality" not in props
    assert "_ModelFirstVertex" in props


@pytest.mark.unit
def test_config_schema_injects_model_enum_on_vertices() -> None:
    """Vertex model field must receive enum from connector available_models."""
    schema = _model_first_app().get_config_schema()
    vertex_props = schema["properties"]["_ModelFirstVertex"]["properties"]
    model_prop = vertex_props["model"]
    assert "enum" in model_prop
    assert "gpt-4o-mini" in model_prop["enum"]
    assert "gemini-3.5-flash" in model_prop["enum"]


@pytest.mark.unit
def test_get_config_returns_vertex_model_not_connector_groups() -> None:
    """get_config() must return vertex params, not top-level connector dicts."""
    cfg = _model_first_app().get_config()
    assert "economy" not in cfg
    assert "quality" not in cfg
    assert cfg["_ModelFirstVertex"]["model"] == "gpt-4o-mini"


@pytest.mark.unit
def test_build_usage_edges_skips_llm_edges_for_model_first_vertices() -> None:
    """Model-first vertices must not produce dashed LLM connector usage edges."""
    app = _model_first_app()
    edges = app._build_usage_edges()
    llm_edges = [e for e in edges if e.attributes.get("usage_type") == "llm"]
    assert llm_edges == []
