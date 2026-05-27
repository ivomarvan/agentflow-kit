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

from src.agentflow.describe import Describable, GraphContext, GraphFragment, _dot_node
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

    # ------------------------------------------------------------------
    # Shared diagnostics — available on every connector
    # ------------------------------------------------------------------

    def describe(self) -> str:
        """Return a human-readable summary of the active backend configuration.

        Returns:
            Multi-line string with backend, model, URL, and timeout.
        """
        return self.config.describe()

    # ------------------------------------------------------------------
    # Describable — concrete implementations using self.config
    # ------------------------------------------------------------------

    def get_markdown(self) -> str:
        """Return a Markdown section describing this connector's configuration.

        Returns:
            Markdown string with backend, model, URL, and timeout.
        """
        cfg = self.config
        lines = [
            f"## LLM: `{cfg.backend}` / `{cfg.model}`",
            "",
            f"- Backend: `{cfg.backend}`",
            f"- Model: `{cfg.model}`",
        ]
        if cfg.base_url:
            lines.append(f"- Base URL: `{cfg.base_url}`")
        lines.append(f"- Timeout: {cfg.timeout}s")
        return "\n".join(lines)

    def get_json(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of this connector's configuration.

        Returns:
            Dict with ``backend``, ``model``, ``base_url``, ``timeout`` keys.
        """
        cfg = self.config
        return {
            "backend": cfg.backend,
            "model": cfg.model,
            "base_url": cfg.base_url,
            "timeout": cfg.timeout,
        }

    def get_graphviz_fragment(self, ctx: GraphContext) -> GraphFragment:
        """Return a DOT cylinder node representing this LLM backend.

        Also registers the node in vis.js data via ``ctx.add_node()`` so that
        ``get_html()`` produces a matching interactive node with a Markdown
        tooltip.

        Args:
            ctx: Mutable context for unique ID allocation and vis.js data.

        Returns:
            ``GraphFragment`` with one node statement.
        """
        cfg = self.config
        node_id = ctx.alloc_id(f"llm_{cfg.backend}")
        stmt = _dot_node(
            node_id,
            label=f"{cfg.backend}\\n{cfg.model}",
            tooltip=f"{cfg.backend}: {cfg.model}, timeout={cfg.timeout}s",
            shape="cylinder",
            style="filled",
            fillcolor="lightcyan",
            color="steelblue",
        )
        # Cytoscape: label = class name only (rule: "shape title = class name")
        # Backend/model details are in the tooltip (get_markdown())
        ctx.add_node(
            node_id,
            label=type(self).__name__,
            description_md=self.get_markdown(),
            node_class="llm",
        )
        return GraphFragment(dot_statements=[stmt], root_id=node_id)

    # ------------------------------------------------------------------
    # Argparse hooks — adds connector-specific CLI commands
    # ------------------------------------------------------------------

    def _add_argparse_commands(self, subparsers: Any) -> None:
        """Register ``show`` and ``ping`` subcommands."""
        subparsers.add_parser("show", help="Print connector configuration.")
        p_ping = subparsers.add_parser(
            "ping", help="Send a test request to verify the LLM connection."
        )
        p_ping.add_argument(
            "--prompt",
            default="Say hello in one short sentence.",
            help="Prompt to send (default: 'Say hello in one short sentence.').",
        )

    def _handle_argparse_command(self, args: Any) -> None:
        """Dispatch ``show`` and ``ping`` commands."""
        import sys

        if args.command == "show":
            print(self.describe())

        elif args.command == "ping":
            print(self.describe())
            print()
            try:
                response = self.chat([{"role": "user", "content": args.prompt}])
            except Exception as exc:
                print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"Response : {response.text}")
            if response.usage:
                print(f"Usage    : {response.usage}")

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
