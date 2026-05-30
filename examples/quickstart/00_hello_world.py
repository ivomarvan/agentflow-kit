"""Minimal agentflow hello world: Uppercase → Done.

The simplest possible StateGraph — two vertices, no LLM calls, pure state
transformation. Demonstrates the basic ExampleApp pattern.

Run with:
    uv run python examples/quickstart/00_hello_world.py              # prints HELLO
    uv run python examples/quickstart/00_hello_world.py -h           # help
    uv run python examples/quickstart/00_hello_world.py browser      # graph in browser
    uv run python examples/quickstart/00_hello_world.py graph-html   # save HTML graph
"""

from __future__ import annotations

from dataclasses import dataclass

from agentflow import AgentApp
from agentflow.statemachine import (
    Context,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from agentflow.statemachine.testing import FakeLlmConnector


@dataclass(frozen=True)
class AppState:
    """Immutable state for the hello world graph."""

    text: str = ""


@dataclass
class AppPatch:
    """State patch for the hello world graph."""

    text: str | None = None


class Uppercase(StateVertex):
    """Converts the text field to uppercase."""

    async def run(self, state: AppState, ctx: Context) -> tuple[object, AppPatch]:
        """Return the text uppercased."""
        return StdSignal.ok, AppPatch(text=state.text.upper())


class Done(StateVertex):
    """Terminal vertex — signals that processing is complete."""

    async def run(self, state: AppState, ctx: Context) -> tuple[object, AppPatch]:
        """Signal workflow completion."""
        return StdSignal.done, AppPatch()


class HelloWorldApp(AgentApp):
    """Minimal hello world: Uppercase → Done → StdEnd."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = FakeLlmConnector()
        self.graph = StateGraph(
            start=Uppercase,
            transitions=[
                Transition(Uppercase, StdSignal.ok, Done),
                Transition(Done, StdSignal.done, StdEnd),
            ],
        )

    async def run_workflow(self) -> str | None:
        """Run the hello world workflow and print the result."""
        ctx = Context(connector=self.connector)
        runner = StateGraphRunner(self.graph, ctx)
        final = await runner.run(AppState(text="hello"))
        print(final.text)  # HELLO
        return final.text


if __name__ == "__main__":
    HelloWorldApp().cli(__doc__, name=__name__)
