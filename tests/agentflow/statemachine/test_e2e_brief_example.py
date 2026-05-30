"""End-to-end integration test for the brief §2.5 demo graph."""

import pytest


@pytest.mark.unit
def test_brief_example_runs_to_completion() -> None:
    """Import and run the demo script; assert expected final state.

    Verifies the complete §2.5 graph cycle:
    - Graph terminates without raising any exception.
    - Final messages tuple is non-empty (vertices produced output).
    - iteration equals the expected approval threshold (2 rejections occurred).
    - The final message indicates approval (review accepted the content).
    """
    import importlib

    mod = importlib.import_module("examples.quickstart.01_brief_example")

    final_state = mod.run_demo()

    assert len(final_state.messages) > 0, "No messages produced — graph did not run"
    assert final_state.iteration == mod._APPROVE_AFTER, (
        f"Expected iteration={mod._APPROVE_AFTER}, got {final_state.iteration}"
    )
    approval_msgs = [m for m in final_state.messages if "approved" in m.lower()]
    assert approval_msgs, "No approval message found — graph may not have reached StdEnd"


@pytest.mark.unit
def test_brief_example_message_count_matches_cycles() -> None:
    """Verify message accumulation: 4 messages per cycle × (APPROVE_AFTER + 1) cycles.

    Each full cycle emits: Research, WriteIntro, WriteBody, Review = 4 messages.
    The graph runs for _APPROVE_AFTER rejected cycles plus one final approved cycle.
    """
    import importlib

    mod = importlib.import_module("examples.quickstart.01_brief_example")

    final_state = mod.run_demo()

    expected_cycles = mod._APPROVE_AFTER + 1
    expected_msgs = expected_cycles * 4
    assert len(final_state.messages) == expected_msgs, (
        f"Expected {expected_msgs} messages ({expected_cycles} cycles × 4), "
        f"got {len(final_state.messages)}: {final_state.messages}"
    )


@pytest.mark.unit
def test_brief_example_build_graph_returns_state_graph() -> None:
    """Ensure build_graph() constructs a StateGraph without error.

    Edge case: the graph builder should not require a Context — it only
    wires pre-instantiated vertices into a StateGraph.
    """
    import importlib

    from agentflow.statemachine import StateGraph

    mod = importlib.import_module("examples.quickstart.01_brief_example")

    graph = mod.build_graph()
    assert isinstance(graph, StateGraph)
