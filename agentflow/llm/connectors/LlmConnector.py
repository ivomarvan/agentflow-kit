"""Smart LLM connector that auto-selects the backend from configuration.

``LlmConnector`` is the recommended entry point for all application code.
It reads ``LlmConfig`` from environment variables by default and delegates
to the appropriate low-level backend (``OpenAiConnector`` or
``AnthropicConnector``).

Constructor parameters all default to ``None``, which means the value is
taken from the environment (``.env`` file or shell variables).  Passing an
explicit value overrides only that field::

    # All settings from .env / environment:
    connector = LlmConnector()

    # Override just the model, keep backend and API key from .env:
    connector = LlmConnector(model="gpt-4o")

    # Fully explicit, with a file cache:
    from agentflow.llm.cache import LlmFileCache
    connector = LlmConnector(
        backend="openai",
        model="gpt-4o",
        cache=LlmFileCache(__file__),
    )

    # Pass a pre-built LlmConfig (legacy / advanced usage):
    connector = LlmConnector(config=LlmConfig.from_env())

Pattern: Facade (GoF) — hides backend selection and config resolution
behind a single, simple constructor.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agentflow.llm.LlmConfig import (
    OPENAI_COMPATIBLE_BACKENDS,
    LlmConfig,
)
from agentflow.llm.LlmConnectorBase import LlmConnectorBase

if TYPE_CHECKING:
    from agentflow.llm.cache.LlmCacheBase import LlmCacheBase

logger = logging.getLogger(__name__)


class LlmConnector(LlmConnectorBase):
    """Concrete LLM connector with automatic backend selection.

    Wraps either ``OpenAiConnector`` or ``AnthropicConnector`` based on
    the resolved ``LlmConfig``.  Inherits transparent caching from
    ``LlmConnectorBase``.

    Args:
        config: Pre-built ``LlmConfig``.  When ``None`` the config is
                resolved from environment variables via ``LlmConfig.from_env()``.
                Any keyword overrides (``backend``, ``model``) are applied
                after loading.
        backend: Override the backend name (e.g. ``"openai"``, ``"anthropic"``).
                 ``None`` → read from ``LLM_BACKEND`` env var.
        model: Override the model name (e.g. ``"gpt-4o"``).
               ``None`` → read from ``LLM_MODEL`` env var.
        cache: Optional cache instance.  Responses are served from cache on
               hit and stored on miss.  ``None`` disables caching.

    Raises:
        ValueError: If the resolved backend is not supported.
        RuntimeError: If a cloud backend is selected but the required API
                      key is absent from the environment.
    """

    def __init__(
        self,
        config: LlmConfig | None = None,
        *,
        backend: str | None = None,
        model: str | None = None,
        cache: LlmCacheBase | None = None,
    ) -> None:
        super().__init__(cache=cache)
        if config is None:
            config = LlmConfig.from_env()
        # Apply keyword overrides on top of the resolved config.
        overrides: dict[str, Any] = {}
        if backend is not None:
            overrides["backend"] = backend
        if model is not None:
            overrides["model"] = model
        if overrides:
            config = config.model_copy(update=overrides)

        self._config = config
        self._inner = self._build_inner(config)
        logger.info(
            "LlmConnector ready: backend=%s model=%s cache=%s",
            config.backend,
            config.model,
            type(cache).__name__ if cache else "none",
        )

    # ------------------------------------------------------------------
    # LlmConnectorBase interface
    # ------------------------------------------------------------------

    @property
    def config(self) -> LlmConfig:
        """Active backend configuration."""
        return self._config

    def _do_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        model_override: str | None,
    ):
        # Delegate to the inner backend's public chat() — inner has no cache.
        return self._inner.chat(messages, tools, temperature, model_override)

    async def _do_achat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        model_override: str | None,
    ):
        return await self._inner.achat(messages, tools, temperature, model_override)

    # ------------------------------------------------------------------
    # Graph composition — expose inner backend as nested child
    # ------------------------------------------------------------------

    def _extra_describable_children(self) -> dict[str, LlmConnectorBase]:
        """Expose the inner backend connector as a nested box in the graph.

        Merges cache (from base class) with the backend connector.
        """
        children = super()._extra_describable_children()
        children["backend"] = self._inner
        return children

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _build_inner(config: LlmConfig) -> LlmConnectorBase:
        """Instantiate the low-level backend connector for *config*.

        Args:
            config: Fully resolved ``LlmConfig``.

        Returns:
            A backend-specific ``LlmConnectorBase`` with no cache set.

        Raises:
            ValueError: When ``config.backend`` is not supported.
        """
        if config.backend in OPENAI_COMPATIBLE_BACKENDS:
            from agentflow.llm.connectors.OpenAiConnector import OpenAiConnector
            return OpenAiConnector(config)
        if config.backend == "anthropic":
            from agentflow.llm.connectors.AnthropicConnector import AnthropicConnector
            return AnthropicConnector(config)
        raise ValueError(
            f"No connector implemented for backend={config.backend!r}. "
            f"Supported: {sorted(OPENAI_COMPATIBLE_BACKENDS | {'anthropic'})}"
        )


if __name__ == "__main__":
    import sys

    try:
        connector = LlmConnector()
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    connector.run_argparse(doc=__doc__, name=__name__)
