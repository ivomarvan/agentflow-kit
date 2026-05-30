"""Fake implementations for deterministic testing of state machine graphs.

FakeVertex, FakeLlmConnector, and make_fake_context allow tests to run
state graphs without real LLM calls or complex vertex logic.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from agentflow.llm.ChatResponse import ChatResponse
from agentflow.llm.LlmConfig import LlmConfig
from agentflow.llm.LlmConnector import LlmConnector
from agentflow.statemachine.context import Context
from agentflow.statemachine.vertex import StateVertex


class FakeVertex(StateVertex):
    """Configurable stub vertex that returns a preset signal and patch.

    Counts how many times run() was called — useful for asserting
    fan-out/fan-in behaviour and cycle termination.

    Args:
        signal: The EnumSignal value to return from run().
        patch: The patch object to return from run().
        name: Optional display name for debugging.
        call_count: Shared mutable list; each run() call appends 1.
                    Pass the same list across multiple fakes to aggregate
                    counts without subclassing.
    """

    def __init__(
        self,
        signal: Any,
        patch: Any,
        *,
        name: str | None = None,
        call_count: list[int] | None = None,
    ) -> None:
        self._signal = signal
        self._patch = patch
        self._name = name or type(self).__name__
        self._call_count: list[int] = call_count if call_count is not None else []
        self.calls: int = 0

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:
        """Return the configured signal and patch, increment call counters.

        Args:
            state: Current state snapshot (ignored by the fake).
            ctx: Shared context (ignored by the fake).

        Returns:
            Tuple of (signal, patch) as configured in __init__.
        """
        self.calls += 1
        self._call_count.append(1)
        return self._signal, self._patch

    def __repr__(self) -> str:
        return f"FakeVertex(name={self._name!r}, calls={self.calls})"


class FakeLlmConnector(LlmConnector):  # type: ignore[misc]
    """Deterministic LlmConnector that returns responses from a preset queue.

    Use queue_responses() to configure the sequence of responses before running.
    Raises RuntimeError when the queue is exhausted — prevents silent test failures.
    """

    def __init__(self) -> None:
        super().__init__()
        self._queue: deque[str] = deque()

    @property
    def config(self) -> LlmConfig:
        """Not implemented — FakeLlmConnector has no real backend configuration.

        Raises:
            NotImplementedError: Always; tests should not inspect connector config.
        """
        raise NotImplementedError("FakeLlmConnector has no real LlmConfig")

    def queue_responses(self, responses: list[str]) -> None:
        """Enqueue a list of string responses to be returned by chat() in order.

        Args:
            responses: Ordered list of response strings. Each chat() call
                       consumes the next response from the front of the queue.
        """
        self._queue.extend(responses)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        model_override: str | None = None,
    ) -> ChatResponse:
        """Return the next queued response as a ChatResponse.

        Args:
            messages: Ignored — fake connector does not call any LLM.
            tools: Ignored.
            temperature: Ignored.
            model_override: Ignored.

        Returns:
            ChatResponse with the next queued string as content.

        Raises:
            RuntimeError: When the response queue is empty.
        """
        if not self._queue:
            raise RuntimeError(
                "FakeLlmConnector queue is empty — call queue_responses() before running."
            )
        content = self._queue.popleft()
        return ChatResponse(role="assistant", content=content, tool_calls=None, usage=None)

    async def achat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        model_override: str | None = None,
    ) -> ChatResponse:
        """Async version of chat() — delegates to the sync implementation.

        Safe to call from async context because the fake performs no I/O.

        Args:
            messages: Ignored — fake connector does not call any LLM.
            tools: Ignored.
            temperature: Ignored.
            model_override: Ignored.

        Returns:
            ChatResponse with the next queued string as content.

        Raises:
            RuntimeError: When the response queue is empty.
        """
        return self.chat(messages, tools=tools, temperature=temperature,
                         model_override=model_override)


def make_fake_context(**overrides: Any) -> Context:
    """Create a Context with FakeLlmConnector and sensible test defaults.

    Args:
        **overrides: Any Context field to override
                     (connector, tools, logger, run_id).

    Returns:
        Context instance ready for use in tests without real LLM calls.
    """
    defaults: dict[str, Any] = {
        "connector": FakeLlmConnector(),
        "logger": logging.getLogger("statemachine.test"),
        "run_id": "test-run-id",
    }
    defaults.update(overrides)
    return Context(**defaults)
