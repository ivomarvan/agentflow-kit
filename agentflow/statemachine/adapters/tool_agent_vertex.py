"""ToolAgentVertex — wraps an entire ToolAgent as a single StateVertex.

The agent runs its full ReAct loop (arun) and returns the final answer
as a single atomic graph step. Simplest migration path for existing agents.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agentflow.agents.ToolAgent import ToolAgent
from agentflow.statemachine.signal import StdSignal
from agentflow.statemachine.vertex import StateVertex

if TYPE_CHECKING:
    from agentflow.statemachine.context import Context


class ToolAgentVertex(StateVertex):  # type: ignore[misc]
    """Wrap an entire ToolAgent as a single StateVertex.

    The agent runs its full ReAct loop (arun) and returns the final answer
    as a single atomic graph step. Simplest migration path for existing agents.

    Note: ToolAgentVertex uses agent.arun() with the agent's own connector,
    not ctx.connector. The ctx is accepted per the StateVertex contract
    but is not used for LLM calls.

    Args:
        agent: Configured ToolAgent instance (with connector, tools, system_prompt).
        question_from_state: Callable that receives the current state and returns
            the question string to pass to the agent.
        answer_to_patch: Callable that maps the agent's final answer string to a
            StatePatch (or any patch-compatible object).
        ok_signal: Signal returned after completion (default StdSignal.ok).
    """

    def __init__(
        self,
        agent: ToolAgent,
        question_from_state: Callable[[Any], str],
        answer_to_patch: Callable[[str], Any],
        *,
        ok_signal: Any = StdSignal.ok,
    ) -> None:
        self._agent = agent
        self._question_from_state = question_from_state
        self._answer_to_patch = answer_to_patch
        self._ok_signal = ok_signal

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Run the wrapped ToolAgent and return a routing signal with state patch.

        Extracts the question from the current state, runs the agent's full
        ReAct loop via arun(), and maps the final answer to a StatePatch.

        Args:
            state: Current immutable state snapshot; question is extracted via
                question_from_state.
            ctx: Shared services; accepted per the StateVertex contract but not
                used for LLM calls — the agent uses its own injected connector.

        Returns:
            Tuple of (ok_signal, patch), where patch is produced by answer_to_patch
            from the agent's final answer string.
        """
        question = self._question_from_state(state)
        answer = await self._agent.arun(question)
        return self._ok_signal, self._answer_to_patch(answer)
