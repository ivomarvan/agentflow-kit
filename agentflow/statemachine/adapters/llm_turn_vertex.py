"""LlmTurnVertex — single LLM chat turn as a StateVertex.

Suitable for fine-grained orchestration where each LLM call is an explicit
graph node, without a built-in ReAct loop. The vertex calls
ctx.connector.achat() directly and maps the ChatResponse to a StatePatch
via a user-supplied callable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agentflow.llm.ChatResponse import ChatResponse
from agentflow.statemachine.signal import StdSignal
from agentflow.statemachine.vertex import LlmStateVertex

if TYPE_CHECKING:
    from agentflow.statemachine.context import Context


class LlmTurnVertex(LlmStateVertex):  # type: ignore[misc]
    """Single LLM chat turn as a StateVertex — no ReAct loop.

    Calls ctx.connector.achat with messages extracted from state.
    Suitable for fine-grained orchestration where each LLM call is
    an explicit graph node.

    Args:
        messages_from_state: Callable that receives the current state and
            returns a list of OpenAI-format message dicts to send to the LLM.
        response_to_patch: Callable that maps the ChatResponse to a StatePatch
            (or any patch-compatible object).
        tools: Optional list of OpenAI-format tool schemas to pass to the LLM.
        temperature: Sampling temperature forwarded to achat (default 0.2).
        ok_signal: Signal returned after a successful LLM turn (default StdSignal.ok).
    """

    def __init__(
        self,
        messages_from_state: Callable[[Any], list[dict[str, Any]]],
        response_to_patch: Callable[[ChatResponse], Any],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        ok_signal: Any = StdSignal.ok,
    ) -> None:
        super().__init__()
        self._messages_from_state = messages_from_state
        self._response_to_patch = response_to_patch
        self._tools = tools
        self._temperature = temperature
        self._ok_signal = ok_signal

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Execute one LLM chat turn and return a routing signal with state patch.

        Builds the messages list from state, calls ctx.connector.achat, and
        maps the ChatResponse to a patch via response_to_patch.

        Args:
            state: Current immutable state snapshot passed to messages_from_state.
            ctx: Shared services; ctx.connector.achat is called for the LLM turn.

        Returns:
            Tuple of (ok_signal, patch), where patch is produced by
            response_to_patch from the ChatResponse.
        """
        messages = self._messages_from_state(state)
        response = await ctx.llm_for_model(self.model).achat(
            messages, tools=self._tools, temperature=self._temperature
        )
        return self._ok_signal, self._response_to_patch(response)
