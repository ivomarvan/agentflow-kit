"""Demo: wrapping an existing ToolAgent as a single StateGraph vertex.

Demonstrates the simplest migration path for existing ToolAgent instances:
wrap the agent in ToolAgentVertex and run it as a single atomic graph step.

Graph topology:
    ToolAgentVertex ──ok──> StdEnd

FakeLlmConnector is used so no real API key is needed.

Run with:
    python src/examples/statemachine_demos/02_tool_agent_demo.py
"""

from git_root_to_syspath import agr  # locate project root and add it to sys.path

PROJECT_ROOT = agr()

import dataclasses  # noqa: E402
from typing import cast  # noqa: E402

from src.agentflow.agents.ToolAgent import ToolAgent  # noqa: E402
from src.agentflow.statemachine import (  # noqa: E402
    Context,
    StateGraph,
    StateGraphRunner,
    StdEnd,
    StdSignal,
    ToolAgentVertex,
    Transition,
)
from src.agentflow.statemachine.testing import FakeLlmConnector  # noqa: E402

# ---------------------------------------------------------------------------
# State and patch dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class DemoState:
    """Immutable state for the tool-agent demo.

    Attributes:
        question: The question passed to the ToolAgent.
        answer: The final answer returned by the ToolAgent.
    """

    question: str = ""
    answer: str = ""


@dataclasses.dataclass
class DemoPatch:
    """Mutable patch applied after ToolAgentVertex completes.

    Attributes:
        answer: New answer string; None means leave unchanged.
    """

    answer: str | None = None


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph(agent: ToolAgent) -> StateGraph:
    """Construct a single-node graph wrapping the provided ToolAgent.

    Args:
        agent: Configured ToolAgent to wrap as a vertex.

    Returns:
        StateGraph with ToolAgentVertex as the sole processing node.
    """
    agent_vertex = ToolAgentVertex(
        agent=agent,
        question_from_state=lambda state: cast(DemoState, state).question,
        answer_to_patch=lambda ans: DemoPatch(answer=ans),
    )
    return StateGraph(
        start=agent_vertex,
        transitions=[
            Transition(agent_vertex, StdSignal.ok, StdEnd),
        ],
    )


# ---------------------------------------------------------------------------
# Demo entry-point
# ---------------------------------------------------------------------------


def run_demo() -> DemoState:
    """Build the graph and run a single question through the ToolAgent.

    Configures a FakeLlmConnector that immediately returns a final-answer
    response (no tool calls), so the agent completes in one step.

    Returns:
        Final DemoState with the answer field populated.
    """
    connector = FakeLlmConnector()
    # Queue a plain-text final answer — no tool_calls, so arun() terminates immediately.
    connector.queue_responses(["50"])

    agent = ToolAgent(
        connector=connector,
        tools=[],
        system_prompt="You are a helpful math assistant.",
        name="demo_agent",
    )

    graph = build_graph(agent)
    # ctx.connector is not used by ToolAgentVertex; a fresh FakeLlmConnector suffices.
    ctx = Context(connector=FakeLlmConnector())
    runner = StateGraphRunner(graph=graph, context=ctx)

    initial_state = DemoState(question="What is 42 + 8?")
    result = runner.run_sync(initial_state)
    return cast(DemoState, result)


if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s — %(message)s",
    )

    final_state = run_demo()
    print(f"Question: {final_state.question}")
    print(f"Answer: {final_state.answer}")
