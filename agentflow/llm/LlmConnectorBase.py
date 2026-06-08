"""Abstract base class and template-method framework for all LLM connectors.

Every concrete connector (OpenAiConnector, AnthropicConnector, FakeLlmConnector, …)
inherits from ``LlmConnectorBase`` and implements only the two private methods
``_do_chat()`` and ``_do_achat()``.  The public ``chat()`` / ``achat()`` methods
are provided here as final template methods that transparently apply the optional
cache before/after delegating to the concrete implementation.

Usage::

    class MyConnector(LlmConnectorBase):
        def _do_chat(self, messages, tools, temperature, model_override):
            ...
        async def _do_achat(self, messages, tools, temperature, model_override):
            ...
        @property
        def config(self) -> LlmConfig:
            ...

Pattern: Template Method (GoF) — LlmConnectorBase defines the algorithm skeleton;
subclasses fill in the backend-specific steps.
"""

from __future__ import annotations

import hashlib
import json
import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from agentflow.describable.describable import Describable
from agentflow.llm.ChatResponse import ChatResponse

if TYPE_CHECKING:
    from agentflow.llm.cache.LlmCacheBase import LlmCacheBase
    from agentflow.llm.LlmConfig import LlmConfig

logger = logging.getLogger(__name__)


def _make_cache_key(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    model: str,
    temperature: float,
) -> str:
    """Compute a stable SHA-256 cache key for an LLM call.

    Including model and temperature ensures cache correctness when multiple
    connectors share one LlmFileCache instance.

    Args:
        messages: Full conversation history in OpenAI format.
        tools: Tool schema list, or None.
        model: Active model name (e.g. 'gpt-4o-mini').
        temperature: Sampling temperature for this call.

    Returns:
        64-character lowercase hex digest.
    """
    payload = json.dumps(
        {"model": model, "temperature": temperature, "messages": messages, "tools": tools},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class LlmConnectorBase(Describable):
    """Abstract base for all LLM backend connectors with optional cache injection.

    Subclasses must implement:
      - ``_do_chat()``   — the synchronous network/computation call
      - ``_do_achat()``  — the async counterpart
      - ``config``       — read-only property returning the active ``LlmConfig``

    The public ``chat()`` and ``achat()`` template methods check the injected
    cache before and after calling the concrete implementation, providing
    transparent caching to every subclass at zero extra effort.

    Args:
        cache: Optional ``LlmCacheBase`` instance.  When provided, responses
               are served from cache on hit and stored on miss.  ``None``
               disables caching (default).
    """

    def __init__(self, *, cache: LlmCacheBase | None = None) -> None:
        super().__init__()
        self._cache = cache

    # ------------------------------------------------------------------
    # Abstract interface — every backend must implement these
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def config(self) -> LlmConfig:
        """Read-only access to the active backend configuration."""
        ...

    @abstractmethod
    def _do_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        model_override: str | None,
    ) -> ChatResponse:
        """Backend-specific synchronous chat implementation.

        Called by ``chat()`` after a cache miss (or when no cache is set).

        Args:
            messages: OpenAI-format conversation history.
            tools: Tool schema list, or None.
            temperature: Sampling temperature.
            model_override: Per-call model name override.

        Returns:
            Fresh ChatResponse from the backend.
        """
        ...

    @abstractmethod
    async def _do_achat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        model_override: str | None,
    ) -> ChatResponse:
        """Backend-specific asynchronous chat implementation.

        Called by ``achat()`` after a cache miss (or when no cache is set).

        Args:
            messages: OpenAI-format conversation history.
            tools: Tool schema list, or None.
            temperature: Sampling temperature.
            model_override: Per-call model name override.

        Returns:
            Fresh ChatResponse from the backend.
        """
        ...

    # ------------------------------------------------------------------
    # Template methods — public API, final (not intended to be overridden)
    # ------------------------------------------------------------------

    @property
    def _model_label(self) -> str:
        """Return a log-safe model identifier without raising on fake connectors."""
        try:
            return self.config.model
        except (NotImplementedError, AttributeError):
            return type(self).__name__

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        model_override: str | None = None,
    ) -> ChatResponse:
        """Send a synchronous chat request, transparently serving from cache.

        Args:
            messages: OpenAI-format conversation history.
            tools: Optional tool schema list.
            temperature: Sampling temperature; lower values are more deterministic.
            model_override: Per-call model name override.

        Returns:
            ``ChatResponse`` — from cache on hit, from backend on miss.

        Raises:
            Exception: Backend-specific error on network, auth, or quota failures.
        """
        if self._cache is not None:
            effective_model = model_override or self.config.model
            key = _make_cache_key(messages, tools, model=effective_model, temperature=temperature)
            hit = self._cache.get(key)
            if hit is not None:
                logger.info("llm_call: model=%s  ← cache hit", self._model_label)
                return hit
            logger.info("llm_call: model=%s  [cache miss]", self._model_label)
            response = self._do_chat(messages, tools, temperature, model_override)
            self._cache.put(key, response)
            logger.debug(
                "cache: stored  (%d/%d)", self._cache.size, getattr(self._cache, "max_size", "?")
            )
            return response
        logger.info("llm_call: model=%s", self._model_label)
        return self._do_chat(messages, tools, temperature, model_override)

    async def achat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        model_override: str | None = None,
    ) -> ChatResponse:
        """Send an asynchronous chat request, transparently serving from cache.

        Args:
            messages: OpenAI-format conversation history.
            tools: Optional tool schema list.
            temperature: Sampling temperature.
            model_override: Per-call model name override.

        Returns:
            ``ChatResponse`` — from cache on hit, from backend on miss.

        Raises:
            Exception: Backend-specific error on network, auth, or quota failures.
        """
        if self._cache is not None:
            effective_model = model_override or self.config.model
            key = _make_cache_key(messages, tools, model=effective_model, temperature=temperature)
            hit = self._cache.get(key)
            if hit is not None:
                logger.info("llm_call: model=%s  ← cache hit", self._model_label)
                return hit
            logger.info("llm_call: model=%s  [cache miss]", self._model_label)
            response = await self._do_achat(messages, tools, temperature, model_override)
            self._cache.put(key, response)
            logger.debug(
                "cache: stored  (%d/%d)", self._cache.size, getattr(self._cache, "max_size", "?")
            )
            return response
        logger.info("llm_call: model=%s", self._model_label)
        return await self._do_achat(messages, tools, temperature, model_override)

    async def achat_with_tools(
        self,
        messages: list[dict[str, Any]],
        registry: Any,  # ToolRegistry — Any to avoid circular import
        max_rounds: int = 10,
        temperature: float = 0.2,
        log: logging.Logger | None = None,
    ) -> Any:  # ChatResponse
        """Execute LLM with automatic tool-calling loop.

        Runs: LLM call → if response has tool_calls: execute each tool via
        registry, append tool result messages → LLM call again → repeat.
        Stops when LLM returns no tool_calls OR max_rounds is exhausted.

        Args:
            messages:    Initial conversation messages.
            registry:    ToolRegistry instance to execute tool calls.
            max_rounds:  Maximum number of LLM+tool-execute iterations.
            temperature: Sampling temperature for all LLM calls.
            log:         Optional logger for tool call INFO messages.

        Returns:
            Final ChatResponse with plain text (no tool_calls).
        """
        import json as _json

        _log = log or logger
        current_messages = list(messages)
        for _ in range(max_rounds):
            response = await self.achat(
                current_messages,
                tools=registry.schemas(),
                temperature=temperature,
            )
            if not response.has_tool_calls:
                return response
            # append assistant message with tool calls
            current_messages.append(response.to_message_dict())
            # execute each tool call
            for tc in (response.tool_calls or []):
                try:
                    args: dict[str, Any] = _json.loads(tc.arguments or "{}")
                except _json.JSONDecodeError:
                    args = {}
                args_fmt = ", ".join(f"{k}={v!r}" for k, v in args.items())
                _log.info("tool_call: %s(%s)", tc.name, args_fmt)
                try:
                    result = registry.execute(tc.name, tc.arguments or "{}")
                except Exception as exc:
                    result = f"ERROR: {exc}"
                _log.info("tool_result: %s → %.120s", tc.name, result)
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                })
        # max_rounds reached — do a final call without tools
        _log.warning("achat_with_tools: max_rounds=%d reached", max_rounds)
        return await self.achat(current_messages, temperature=temperature)

    # ------------------------------------------------------------------
    # Shared diagnostics
    # ------------------------------------------------------------------

    def describe(self) -> str:
        """Return a human-readable summary of the active backend configuration.

        Returns:
            Multi-line string from the underlying LlmConfig, or a basic
            string for connectors that do not expose a real config.
        """
        try:
            return self.config.describe()
        except NotImplementedError:
            return f"{type(self).__name__} (no config)"

    def _get_own_attributes(self) -> dict[str, Any]:
        """Expose cache, backend, and model in graph tooltips and descriptions."""
        attrs = super()._get_own_attributes()
        if self._cache is not None:
            attrs["cache"] = type(self._cache).__name__
        try:
            cfg = self.config
        except NotImplementedError:
            return attrs
        attrs["backend"] = cfg.backend
        attrs["model"] = cfg.model
        return attrs

    def _extra_describable_children(self) -> dict[str, Any]:
        """Expose the injected cache as a nested box in the composition graph."""
        if self._cache is not None:
            return {"cache": self._cache}
        return {}

    def __str__(self) -> str:
        return f"{type(self).__name__}({self.config})"

    def __repr__(self) -> str:
        try:
            return f"{type(self).__name__}(config={self.config!r})"
        except NotImplementedError:
            return f"{type(self).__name__}()"
