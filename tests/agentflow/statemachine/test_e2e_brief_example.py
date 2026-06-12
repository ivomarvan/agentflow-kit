"""End-to-end integration test for the brief §2.5 demo graph."""

import pytest


@pytest.mark.unit
def test_brief_example_runs_to_completion() -> None:
    """Instantiate BriefExampleApp and run the workflow; assert expected final state."""
    import importlib
    from typing import cast

    mod = importlib.import_module("examples.framework.02_parallel_and_loop")

    app = mod.BriefExampleApp()
    from agentflow.llm.LlmPool import LlmPool
    from agentflow.statemachine import Context, StateGraphRunner

    ctx = Context(pool=LlmPool.from_connector(mod._connector))
    runner = StateGraphRunner(graph=app.graph, context=ctx)
    final_state = cast(mod.DemoState, runner.run_sync(mod.DemoState()))

    assert len(final_state.messages) > 0, "No messages produced — graph did not run"
    assert final_state.iteration == mod._APPROVE_AFTER, (
        f"Expected iteration={mod._APPROVE_AFTER}, got {final_state.iteration}"
    )
    approval_msgs = [m for m in final_state.messages if "approved" in m.lower()]
    assert approval_msgs, "No approval message found — graph may not have reached StdEnd"


@pytest.mark.unit
def test_brief_example_message_count_matches_cycles() -> None:
    """Verify message accumulation: 4 messages per cycle × (APPROVE_AFTER + 1) cycles."""
    import importlib
    from typing import cast

    mod = importlib.import_module("examples.framework.02_parallel_and_loop")

    app = mod.BriefExampleApp()
    from agentflow.llm.LlmPool import LlmPool
    from agentflow.statemachine import Context, StateGraphRunner

    ctx = Context(pool=LlmPool.from_connector(mod._connector))
    runner = StateGraphRunner(graph=app.graph, context=ctx)
    final_state = cast(mod.DemoState, runner.run_sync(mod.DemoState()))

    expected_cycles = mod._APPROVE_AFTER + 1
    expected_msgs = expected_cycles * 4
    assert len(final_state.messages) == expected_msgs, (
        f"Expected {expected_msgs} messages ({expected_cycles} cycles × 4), "
        f"got {len(final_state.messages)}: {final_state.messages}"
    )


@pytest.mark.unit
def test_brief_example_app_graph_is_state_graph() -> None:
    """Ensure BriefExampleApp.graph is a StateGraph instance constructed without error."""
    import importlib

    from agentflow.statemachine import StateGraph

    mod = importlib.import_module("examples.framework.02_parallel_and_loop")

    app = mod.BriefExampleApp()
    assert isinstance(app.graph, StateGraph)
