"""Demo: wrapping an existing ToolAgent as a single StateGraph vertex.

Demonstrates the simplest migration path for existing ToolAgent instances:
wrap the agent in ToolAgentVertex and run it as a single atomic graph step.

Graph topology:
    ToolAgentVertex ──ok──> StdEnd

FakeLlmConnector is used so no real API key is needed.

Run with:
    uv run python examples/quickstart/02_tool_agent_demo.py              # run workflow
    uv run python examples/quickstart/02_tool_agent_demo.py -h           # help
    uv run python examples/quickstart/02_tool_agent_demo.py browser      # graph in browser
    uv run python examples/quickstart/02_tool_agent_demo.py graph-html   # save HTML graph
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


class ToolAgentDemoApp(AgentApp):
    """Demonstrates wrapping a ToolAgent as a single StateGraph vertex."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = FakeLlmConnector()
        # Queue a plain-text final answer — no tool_calls, so arun() terminates immediately.
        self.connector.queue_responses(["50"])
        self.agent = ToolAgent(
            connector=self.connector,
            tools=[],
            system_prompt="You are a helpful math assistant.",
            name="demo_agent",
        )
        agent_vertex = ToolAgentVertex(
            agent=self.agent,
            question_from_state=lambda state: state.question,  # type: ignore[union-attr]
            answer_to_patch=lambda ans: DemoPatch(answer=ans),
        )
        self.graph = StateGraph(
            start=agent_vertex,
            transitions=[
                Transition(agent_vertex, StdSignal.ok, StdEnd),
            ],
        )

    async def run_workflow(self) -> str | None:
        """Run the ToolAgent demo graph and print the question and answer."""
        # ctx.connector is not used by ToolAgentVertex; a fresh FakeLlmConnector suffices.
        ctx = Context(connector=FakeLlmConnector())
        runner = StateGraphRunner(graph=self.graph, context=ctx)
        initial_state = DemoState(question="What is 42 + 8?")
        final_state: DemoState = await runner.run(initial_state)  # type: ignore[assignment]
        print(f"Question: {final_state.question}")
        print(f"Answer: {final_state.answer}")
        return None


if __name__ == "__main__":
    ToolAgentDemoApp().cli(__doc__, name=__name__)
