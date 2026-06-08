"""Demo: wrapping an existing ToolAgent as a single StateGraph vertex.

Demonstrates the simplest migration path for existing ToolAgent instances:
wrap the agent in ToolAgentVertex and run it as a single atomic graph step.

Graph topology:
    ToolAgentVertex ──ok──> StdEnd

FakeLlmConnector is used so no real API key is needed.

Run with:
    uv run python examples/quickstart/02_tool_agent_demo.py -h           # help
    uv run python examples/quickstart/02_tool_agent_demo.py run        # run workflow
    uv run python examples/quickstart/02_tool_agent_demo.py graph --browser
    uv run python examples/quickstart/02_tool_agent_demo.py graph -o graph.html
"""

import dataclasses

from agentflow import AgentApp
from agentflow.agents.ToolAgent import ToolAgent
from agentflow.statemachine import (
    Context,
    StateGraph,
    StateGraphRunner,
    StdEnd,
    StdSignal,
    ToolAgentVertex,
    Transition,
)
from agentflow.statemachine.testing import FakeLlmConnector


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


_connector = FakeLlmConnector()
# Queue a plain-text final answer — no tool_calls, so arun() terminates immediately.
_connector.queue_responses(["50"])
_agent = ToolAgent(
    connector=_connector,
    tools=[],
    system_prompt="You are a helpful math assistant.",
    name="demo_agent",
)
_agent_vertex = ToolAgentVertex(
    agent=_agent,
    question_from_state=lambda state: state.question,  # type: ignore[union-attr]
    answer_to_patch=lambda ans: DemoPatch(answer=ans),
)

_app = AgentApp(
    doc=__doc__,
    context=Context(),
    state_graph=StateGraph(
        start=_agent_vertex,
        transitions=[Transition(_agent_vertex, StdSignal.ok, StdEnd)],
    ),
    initial_state_factory=lambda _q: DemoState(question="What is 42 + 8?"),
)

_app._extract_result = lambda state: state.answer or None  # type: ignore[method-assign, attr-defined]

if __name__ == "__main__":
    _app.cli(__doc__, name=__name__)
