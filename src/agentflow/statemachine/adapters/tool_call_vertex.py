"""ToolCallVertex — wraps a single ToolBase call as a StateVertex.

The vertex extracts tool arguments from the current state, serialises them
to JSON, runs the synchronous tool in a thread pool via ctx.run_sync, and
maps the result string back to a StatePatch via a user-supplied callable.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.agentflow.statemachine.signal import StdSignal
from src.agentflow.statemachine.vertex import StateVertex
from src.agentflow.tools.Tool import ToolBase

if TYPE_CHECKING:
    from src.agentflow.statemachine.context import Context

logger = logging.getLogger(__name__)


class ToolCallVertex(StateVertex):  # type: ignore[misc]
    """Wrap a single ToolBase call as a StateVertex.

    Extracts tool arguments from the current state via args_from_state,
    executes the tool synchronously (in a thread via ctx.run_sync), and
    maps the result string to a StatePatch via result_to_patch.

    All __init__ params have defaults (ok_signal, fail_signal) for VertexResolver
    compatibility, EXCEPT tool/args_from_state/result_to_patch which must be
    provided. Users should always pass instances explicitly.

    Args:
        tool: ToolBase instance to execute.
        args_from_state: Callable that receives the current state and returns
            a dict of keyword arguments for the tool. The dict is serialised
            to a JSON string before being passed to tool.execute().
        result_to_patch: Callable that maps the tool result string to a
            StatePatch (or any patch-compatible object).
        ok_signal: Signal returned on successful execution (default StdSignal.ok).
        fail_signal: Signal returned when an exception is raised (default StdSignal.fail).
    """

    def __init__(
        self,
        tool: ToolBase,
        args_from_state: Callable[[Any], dict[str, Any]],
        result_to_patch: Callable[[str], Any],
        *,
        ok_signal: Any = StdSignal.ok,
        fail_signal: Any = StdSignal.fail,
    ) -> None:
        self._tool = tool
        self._args_from_state = args_from_state
        self._result_to_patch = result_to_patch
        self._ok_signal = ok_signal
        self._fail_signal = fail_signal

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Execute the wrapped tool and return a routing signal with state patch.

        Extracts arguments from state, serialises to JSON, and runs the tool
        synchronously in a thread pool so the event loop is not blocked.
        On any exception, logs the error at EXCEPTION level and returns the
        fail signal with an empty-result patch.

        Args:
            state: Current immutable state snapshot passed to args_from_state.
            ctx: Shared services; ctx.run_sync is used to offload the blocking call.

        Returns:
            Tuple of (ok_signal, patch) on success, or (fail_signal, patch) on error,
            where patch is produced by result_to_patch from the tool result string.
        """
        try:
            args = self._args_from_state(state)
            result: Any = await ctx.run_sync(self._tool.execute, json.dumps(args))
            return self._ok_signal, self._result_to_patch(result)
        except Exception:
            logger.exception("ToolCallVertex failed: tool=%s", type(self._tool).__name__)
            return self._fail_signal, self._result_to_patch("")
