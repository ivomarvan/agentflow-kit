"""Smoke tests — examples must expose declarative AgentApp instances."""
from __future__ import annotations

import importlib

import pytest

from agentflow import AgentApp

DECLARATIVE_MODULES = [
    "examples.agents.01_tool_calling_agent",
    "examples.agents.02_react_agent",
    "examples.agents.03_rag_review_loop",
    "examples.agents.04_blog_pipeline",
    "examples.agents.05_validated_tools",
    "examples.quickstart.00_hello_world",
    "examples.quickstart.01_brief_example",
    "examples.quickstart.02_tool_agent_demo",
    "examples.quickstart.03_live_graph_demo",
    "examples.quickstart.04_parallel_research_loop",
    "examples.showcase",
]


@pytest.mark.unit
@pytest.mark.parametrize("module_path", DECLARATIVE_MODULES)
def test_example_has_no_agentapp_subclass(module_path: str) -> None:
    """Each example must expose an AgentApp instance, not a subclass."""
    mod = importlib.import_module(module_path)
    app = getattr(mod, "_app", None) or getattr(mod, "app", None)
    assert app is not None, f"{module_path} must expose '_app' or 'app'"
    assert type(app) is AgentApp, (
        f"{module_path}: expected AgentApp instance, got {type(app).__name__}"
    )
