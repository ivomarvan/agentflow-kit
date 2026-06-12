"""Smoke tests — examples must expose declarative AgentApp instances."""
from __future__ import annotations

import importlib

import pytest

from agentflow import AgentApp

DECLARATIVE_MODULES = [
    # framework/ — state machine mechanics (no or mock LLM)
    "examples.framework.01_hello_state_machine",
    "examples.framework.02_parallel_and_loop",
    "examples.framework.03_live_graph",
    "examples.framework.04_checkpoint_resume",
    # agents/ — agent patterns with real LLM
    "examples.agents.01_tool_calling",
    "examples.agents.02_react_agent",
    "examples.agents.03_review_loop",
    "examples.agents.04_pipeline",
    "examples.agents.05_validated_tools",
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
