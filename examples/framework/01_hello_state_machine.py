"""Minimal agentflow hello world: Uppercase → Done.

The simplest possible StateGraph — two vertices, no LLM calls, pure state
transformation. Demonstrates the basic ExampleApp pattern.
"""

# Run:
#     uv run python examples/framework/01_hello_state_machine.py -h           # help (all subcommands)
#     uv run python examples/framework/01_hello_state_machine.py run          # prints HELLO
#     uv run python examples/framework/01_hello_state_machine.py graph --browser
#     uv run python examples/framework/01_hello_state_machine.py graph -o graph.html

from __future__ import annotations

from dataclasses import dataclass

from agentflow import AgentApp
from agentflow.statemachine import (
    Context,
    StateGraph,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)


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


_app = AgentApp(
    doc=__doc__,
    default_question="hello",
    context=Context(),
    state_graph=StateGraph(
        start=Uppercase,
        transitions=[
            Transition(Uppercase, StdSignal.ok, Done),
            Transition(Done, StdSignal.done, StdEnd),
        ],
    ),
    initial_state_factory=lambda q: AppState(text=q or "hello"),
)

_app._extract_result = lambda state: state.text  # type: ignore[method-assign, attr-defined]

if __name__ == "__main__":
    _app.cli(__doc__, name=__name__)
