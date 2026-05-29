"""Abstract connector interface and factory for LLM backends.

LlmConnector defines the contract that all backend-specific connectors must
fulfil: accept a list of messages, return a typed ChatResponse.  It contains
no network code itself.

Concrete implementations live in separate files:
  - OpenAiConnector  — OpenAI-compatible backends (openai, ollama, gemini, deepseek)
  - AnthropicConnector — Anthropic native API (claude-* models)

Use the factory to get the right connector for a config::

    connector = LlmConnector.create(LlmConfig.from_env())
    response = connector.chat([{"role": "user", "content": "Hello!"}])
    print(response.text)

Pattern: Abstract Factory (GoF) — LlmConnector.create() selects the concrete
implementation based on the backend stored in LlmConfig.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any

from git_root_to_syspath import agr  # locate project root and add it to sys.path
agr()

from src.agentflow.describable.describable import Describable
from src.agentflow.llm.ChatResponse import ChatResponse
from src.agentflow.llm.LlmConfig import LlmConfig, OPENAI_COMPATIBLE_BACKENDS

logger = logging.getLogger(__name__)


class LlmConnector(Describable):
    """Abstract base class defining the interface for all LLM backend connectors.

    Responsibilities:
      - Declare the ``chat()`` contract that every backend must implement.
      - Provide the ``create()`` factory that selects the correct subclass.
      - Offer shared diagnostic helpers (``describe()``, ``__str__``).

    Not responsible for: tool execution, conversation history, retry loops,
    streaming, token counting — those belong in higher-level components built
    on top of this interface.
    """

    # ------------------------------------------------------------------
    # Abstract interface — every backend must implement these
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def config(self) -> LlmConfig:
        """Read-only access to the backend configuration."""
        ...

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        model_override: str | None = None,
    ) -> ChatResponse:
        """Send a chat completion request and return a normalised response.

        Args:
            messages: List of message dicts in OpenAI format
                      (``{"role": "user"|"assistant"|"system", "content": "..."}``)
            tools: Optional list of OpenAI-format tool definitions.  Pass
                   ``ToolRegistry.schemas()`` here to enable tool-calling.
            temperature: Sampling temperature; lower values are more deterministic.
            model_override: Per-call model name override.  Uses ``config.model``
                            when ``None``.

        Returns:
            ``ChatResponse`` with role, content, tool_calls, and usage information.

        Raises:
            Exception: Backend-specific error on network, auth, or quota failures.
        """
        ...

    @abstractmethod
    async def achat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        model_override: str | None = None,
    ) -> ChatResponse:
        """Async counterpart to chat() — native coroutine, no thread pool needed.

        Args:
            messages: List of message dicts in OpenAI format.
            tools: Optional list of OpenAI-format tool definitions.
            temperature: Sampling temperature.
            model_override: Per-call model name override.

        Returns:
            ChatResponse with role, content, tool_calls, and usage.

        Raises:
            Exception: Backend-specific error on network, auth, or quota failures.
        """
        ...

    # ------------------------------------------------------------------
    # Shared diagnostics — available on every connector
    # ------------------------------------------------------------------

    def describe(self) -> str:
        """Return a human-readable summary of the active backend configuration.

        Returns:
            Multi-line string with backend, model, URL, and timeout.
        """
        return self.config.describe()

    def __str__(self) -> str:
        return f"{type(self).__name__}({self.config})"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(config={self.config!r})"

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def create(config: LlmConfig) -> LlmConnector:
        """Instantiate the correct connector subclass for the given config.

        Args:
            config: Resolved ``LlmConfig`` (use ``LlmConfig.from_env()``).

        Returns:
            A concrete ``LlmConnector`` subclass ready to call ``chat()``.

        Raises:
            ValueError: If the backend in ``config`` is not supported.
        """
        if config.backend in OPENAI_COMPATIBLE_BACKENDS:
            from src.agentflow.llm.connectors.OpenAiConnector import OpenAiConnector
            return OpenAiConnector(config)
        if config.backend == "anthropic":
            from src.agentflow.llm.connectors.AnthropicConnector import AnthropicConnector
            return AnthropicConnector(config)
        raise ValueError(
            f"No connector implemented for backend={config.backend!r}. "
            f"Supported: {sorted(OPENAI_COMPATIBLE_BACKENDS | {'anthropic'})}"
        )


if __name__ == "__main__":
    import sys

    try:
        connector = LlmConnector.create(LlmConfig.from_env())
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    connector.run_argparse(doc=__doc__, name=__name__)
