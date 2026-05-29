"""Shared pytest fixtures for src/agentflow/tests/statemachine/.

Re-exports fixtures from the production testing utilities module so they are
discovered automatically by pytest without explicit imports in each test file.
"""

from src.agentflow.statemachine.testing.fixtures import fake_ctx, make_state_graph

__all__ = ["fake_ctx", "make_state_graph"]
