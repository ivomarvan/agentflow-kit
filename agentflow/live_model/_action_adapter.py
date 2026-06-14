"""Internal ToolBase adapter wrapping a LiveModel @action method."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from agentflow.live_model._schema import build_action_parameters_schema
from agentflow.tools.Tool import ToolBase

_logger = logging.getLogger(__name__)


class _ActionToolAdapter(ToolBase):
    """Wrap a single @action method as a ToolBase for LLM and demo use.

    Args:
        model: LiveModel instance that owns the bound method.
        method: Bound @action method to invoke on execute().
    """

    def __init__(self, model: Any, method: Callable[..., Any]) -> None:
        super().__init__(name=method.__name__)
        self._model = model
        self._method = method
        doc = inspect.getdoc(method) or ""
        first_line = doc.split("\n", 1)[0].strip()
        object.__setattr__(self, "description", first_line)

    def parameters_schema(self) -> dict[str, Any]:
        """Return JSON Schema derived from the @action method signature."""
        return build_action_parameters_schema(self._method.__func__)  # type: ignore[attr-defined]

    def execute(self, **kwargs: Any) -> str:
        """Call the underlying @action method and return a string result."""
        try:
            result = self._method(**kwargs)
            return str(result)
        except Exception as exc:  # noqa: BLE001 — tools must not raise
            _logger.warning(
                "Action %s failed: %s", self.name, exc, exc_info=True
            )
            return f"Error: {exc}"
