"""Smart LLM connector that auto-selects the backend from configuration.

``LlmConnector`` is the recommended entry point for all application code.
It reads ``LlmConfig`` from environment variables by default and delegates
to the appropriate low-level backend (``OpenAiConnector`` or
``AnthropicConnector``).

Constructor parameters default to env-backed values; explicit keyword
arguments override only those fields::

    # All settings from .env / environment:
    connector = LlmConnector()

    # Override just the model, keep backend and API key from .env:
    connector = LlmConnector(model="gpt-4o")

    # Fully explicit, with a file cache:
    from agentflow.llm.cache import LlmFileCache
    connector = LlmConnector(
        model="gpt-4o",
        cache=LlmFileCache(__file__),
    )

Pattern: Facade (GoF) — hides backend selection and config resolution
behind a single, simple constructor.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from agentflow.llm.LlmConfig import (
    OPENAI_COMPATIBLE_BACKENDS,
    LlmConfig,
)
from agentflow.llm.LlmConnectorBase import LlmConnectorBase

logger = logging.getLogger(__name__)


class LlmConnector(BaseModel, LlmConnectorBase):
    """Concrete LLM connector with automatic backend selection.

    Pydantic fields (shown in GUI Settings):
        model   — LLM model name; backend is auto-selected from the name prefix.
        timeout — Request timeout in seconds.

    Infrastructure fields (not shown in GUI):
        cache   — Optional cache instance; excluded from JSON Schema.

    Wraps either ``OpenAiConnector`` or ``AnthropicConnector`` based on
    the resolved ``LlmConfig``.  Inherits transparent caching from
    ``LlmConnectorBase``.

    Raises:
        ValueError: If the resolved backend is not supported.
        RuntimeError: If a cloud backend is selected but the required API
                      key is absent from the environment.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # --- Configurable parameters (appear in GUI) ---
    model: Annotated[
        str,
        Field(
            default="",
            description="LLM model name. Backend is auto-selected from the model prefix.",
        ),
    ] = ""
    timeout: Annotated[
        float,
        Field(default=120.0, gt=0, description="Request timeout in seconds."),
    ] = 120.0

    # --- Infrastructure (not shown in GUI) ---
    cache: Annotated[
        Any,
        Field(default=None, exclude=True),
    ] = None

    # --- Private runtime state ---
    _config: LlmConfig = PrivateAttr(default=None)
    _inner: LlmConnectorBase = PrivateAttr(default=None)

    def model_post_init(self, __context: Any) -> None:
        """Build LlmConfig from env; apply model/timeout overrides; build inner connector."""
        from agentflow.describable.describable import Describable

        # BaseModel init does not run LlmConnectorBase.__init__; set Describable identity.
        Describable.__init__(self)
        object.__setattr__(self, "_cache", self.cache)

        env_config = LlmConfig.from_env()
        overrides: dict[str, Any] = {}
        if self.model:
            overrides["model"] = self.model
        config = env_config.with_overrides(**overrides) if overrides else env_config
        config.timeout = self.timeout
        self._config = config
        self._inner = self._build_inner(config)
        # Sync Pydantic fields with resolved config so GUI reads actual values.
        object.__setattr__(self, "model", config.model)
        object.__setattr__(self, "timeout", config.timeout)
        logger.info(
            "LlmConnector ready: backend=%s model=%s cache=%s",
            config.backend,
            config.model,
            type(self.cache).__name__ if self.cache else "none",
        )

    def __setattr__(self, name: str, value: Any) -> None:
        """Rebuild inner connector when model changes after initial construction."""
        super().__setattr__(name, value)
        if name == "model" and self._inner is not None:
            updated_config = self._config.with_overrides(model=value)
            self._config = updated_config
            self._inner = self._build_inner(updated_config)
            logger.info(
                "LlmConnector model updated: backend=%s model=%s",
                self._config.backend,
                self._config.model,
            )
        elif name == "timeout" and self._config is not None:
            self._config.timeout = value

    # ------------------------------------------------------------------
    # LlmConnectorBase interface
    # ------------------------------------------------------------------

    @property
    def config(self) -> LlmConfig:
        """Active backend configuration."""
        return self._config

    # ------------------------------------------------------------------
    # Describable — config schema (runtime-dynamic enum injection)
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        """Return a JSON Schema exposing only model and timeout.

        The backend is intentionally hidden — it is auto-inferred from the
        model name prefix and not user-configurable.  When ``available_models``
        in the config contains model lists, the model field is rendered as an
        ``enum`` (select box in the GUI).

        Returns:
            JSON-Schema-compatible dict with ``model`` (optional enum) and
            ``timeout`` properties.
        """
        schema = super().get_config_schema()
        properties = dict(schema.get("properties", {}))
        properties.pop("cache", None)

        all_models: list[str] = []
        for backend_models in self._config.available_models.values():
            all_models.extend(backend_models)
        if self._config.model not in all_models:
            all_models.insert(0, self._config.model)

        if "model" in properties and len(all_models) > 1:
            properties["model"] = {**properties["model"], "enum": all_models}

        return {**schema, "properties": properties}

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
