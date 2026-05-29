"""Testing utilities for agentflow.statemachine.

Provides deterministic test doubles and factories for state machine graphs:
- FakeVertex: configurable stub vertex, counts calls.
- FakeLlmConnector: queue-based LLM stub, raises on empty queue.
- make_fake_context: factory for Context without a real LLM.

Import in tests:
    from src.agentflow.statemachine.testing import FakeVertex, make_fake_context
    from src.agentflow.statemachine.testing.fixtures import fake_ctx
"""

from src.agentflow.statemachine.testing.fakes import (
    FakeLlmConnector,
    FakeVertex,
    make_fake_context,
)

__all__ = ["FakeLlmConnector", "FakeVertex", "make_fake_context"]
