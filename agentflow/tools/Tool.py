"""Abstract base class and decorator utilities for stateful LLM tools.

Tools are objects, not functions — they can hold state (API clients, caches,
counters, configuration).  The JSON schema sent to the LLM is derived
automatically from Python type annotations; use ``@param_desc`` to attach
human-readable parameter descriptions without touching the function signature.

Typical usage::

    from agentflow.tools.Tool import ToolBase, param_desc

    class GetWeather(ToolBase):
        \"\"\"Return current weather for a city.\"\"\"

        def __init__(self, api_key: str) -> None:
            self._api_key = api_key  # stateful: owns the HTTP client / key

        @param_desc(city="City name, e.g. 'Prague'")
        def execute(self, city: str) -> str:
            ...  # real HTTP call here
            return f"22 C, sunny in {city}"

Pattern: Strategy (GoF) — each concrete tool is an interchangeable strategy
registered in ToolRegistry.
"""

from __future__ import annotations

import inspect
import logging
import re
from abc import abstractmethod
from collections.abc import Callable
from typing import Any, get_type_hints

from agentflow.describable.describable import Describable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema type mapping
# ---------------------------------------------------------------------------

_PY_TO_JSON_TYPE: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def param_desc(**descriptions: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attach parameter descriptions to a method for JSON schema generation.

    The descriptions are stored as the ``__param_descriptions__`` attribute on
    the decorated function and read by ``ToolBase.parameters_schema()``.

    Args:
        **descriptions: Keyword arguments mapping parameter name to its
                        natural-language description sent to the LLM.

    Returns:
        Decorator that annotates the function and returns it unchanged.

    Example::

        @param_desc(
            city="City name, e.g. 'Prague'",
            unit="Temperature unit: 'celsius' or 'fahrenheit'",
        )
        def execute(self, city: str, unit: str = "celsius") -> str: ...
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__param_descriptions__ = descriptions  # type: ignore[attr-defined]
        return fn

    return decorator


# ---------------------------------------------------------------------------
# Schema builder helpers
# ---------------------------------------------------------------------------


def _camel_to_snake(name: str) -> str:
    """Convert a CamelCase class name to a snake_case tool name.

    Leading underscores (Python private-class convention) are stripped so
    that ``_MyTool`` produces the same tool name as ``MyTool``.

    Args:
        name: CamelCase string, optionally prefixed with underscores.

    Returns:
        snake_case string without leading underscores.
    """
    name = name.lstrip("_")
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _unwrap_optional(py_type: Any) -> Any:
    """Strip ``None`` from ``X | None`` / ``Optional[X]`` and return ``X``.

    Args:
        py_type: A type annotation, possibly a union including ``None``.

    Returns:
        The non-``None`` inner type, or the original type unchanged.
    """
    args = getattr(py_type, "__args__", None)
    if args and type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        return non_none[0] if non_none else str
    return py_type


def build_parameters_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    """Build a JSON Schema ``parameters`` object from a method's type annotations.

    Reads:
      - Type hints for parameter types (mapped to JSON Schema types).
      - Default values to determine required vs optional fields.
      - ``__param_descriptions__`` attribute set by ``@param_desc``.

    Args:
        fn: The ``execute()`` method (or any callable) to inspect.
            ``self`` and ``return`` are excluded automatically.

    Returns:
        JSON Schema dict with ``"type"``, ``"properties"``, and ``"required"``
        keys, suitable for embedding in an OpenAI tool definition.
    """
    try:
        hints = get_type_hints(fn)
    except Exception:  # pragma: no cover — degenerate annotations edge case
        hints = {}

    sig = inspect.signature(fn)
    param_descs: dict[str, str] = getattr(fn, "__param_descriptions__", {})

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        raw_type = hints.get(param_name, str)
        py_type = _unwrap_optional(raw_type)
        json_type = _PY_TO_JSON_TYPE.get(py_type, "string")

        prop: dict[str, Any] = {"type": json_type}
        if param_name in param_descs:
            prop["description"] = param_descs[param_name]

        properties[param_name] = prop

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# ---------------------------------------------------------------------------
# ToolBase
# ---------------------------------------------------------------------------


class ToolBase(Describable):
    """Abstract base class for stateful LLM tools.

    Subclass and implement ``execute()``.  Optionally decorate ``execute()``
    with ``@param_desc`` to attach human-readable parameter descriptions for
    the JSON schema that is sent to the LLM.

    Instances can hold state — API clients, caches, counters, configuration —
    making them more powerful and testable than plain functions.

    Pattern: Strategy (GoF) — each concrete tool is an interchangeable
    strategy registered in ``ToolRegistry``.
    """

    # ------------------------------------------------------------------
    # Identity — override in subclasses when needed
    # ------------------------------------------------------------------

    def __init__(self, name: str | None = None) -> None:
        """Initialise the tool, setting snake_case name and docstring description.

        Args:
            name: Optional explicit tool name.  When omitted, derived from the
                  class name via ``_camel_to_snake()``.
        """
        super().__init__()
        # Override the class-name default with a snake_case tool name for LLM schemas
        self.name = name or _camel_to_snake(type(self).__name__)

    def _get_own_attributes(self) -> dict[str, Any]:
        d = super()._get_own_attributes()
        d["parameters"] = self.parameters_schema()
        return d

    # ------------------------------------------------------------------
    # Contract
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with the given keyword arguments.

        Args:
            **kwargs: Arguments as parsed from the LLM's JSON string.

        Returns:
            Result that will be serialised to string and fed back to the LLM
            as a ``tool`` role message.
        """
        ...

    # ------------------------------------------------------------------
    # Schema generation
    # ------------------------------------------------------------------

    def parameters_schema(self) -> dict[str, Any]:
        """Build a JSON Schema ``parameters`` object from ``execute()`` annotations.

        Returns:
            JSON Schema dict with ``"type"``, ``"properties"``, and ``"required"``.
        """
        return build_parameters_schema(self.execute)

    def to_openai_schema(self) -> dict[str, Any]:
        """Return the full OpenAI function-calling tool definition dict.

        Returns:
            Dict with ``"type": "function"`` and ``"function"`` keys, ready to
            pass as an element of the ``tools`` argument to ``LlmConnector.chat()``.
        """
        schema = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema(),
            },
        }
        logger.debug("Tool schema built: name=%s", self.name)
        return schema

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"
