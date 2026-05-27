"""Abstract base class and decorator utilities for stateful LLM tools.

Tools are objects, not functions — they can hold state (API clients, caches,
counters, configuration).  The JSON schema sent to the LLM is derived
automatically from Python type annotations; use ``@param_desc`` to attach
human-readable parameter descriptions without touching the function signature.

Typical usage::

    from src.agentflow.tools.Tool import ToolBase, param_desc

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

from git_root_to_syspath import agr
agr()

from src.agentflow.describe import Describable, GraphContext, GraphFragment, _dot_node, _esc

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

    @property
    def name(self) -> str:
        """Tool name sent to the LLM.

        Defaults to the class name converted to snake_case.
        Override in subclasses to use a different name.

        Returns:
            Snake_case tool name string.
        """
        return _camel_to_snake(type(self).__name__)

    @property
    def description(self) -> str:
        """Tool description sent to the LLM.

        Defaults to the class docstring.  Override for a custom description.

        Returns:
            Description string.
        """
        return inspect.getdoc(type(self)) or f"Tool: {self.name}"

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
    # Describable — concrete default implementations
    # Subclasses inherit these; override only when custom output is needed.
    # ------------------------------------------------------------------

    def get_markdown(self) -> str:
        """Return a Markdown section describing this tool.

        Returns:
            Markdown string with name, description, and parameters table.
        """
        lines = [f"## Tool: `{self.name}`", "", self.description]
        schema = self.parameters_schema()
        props: dict[str, Any] = schema.get("properties", {})
        required: list[str] = schema.get("required", [])
        if props:
            lines += ["", "**Parameters:**", ""]
            for param_name, prop in props.items():
                req = " *(required)*" if param_name in required else " *(optional)*"
                desc = prop.get("description", "")
                desc_part = f" — {desc}" if desc else ""
                lines.append(f"- `{param_name}` ({prop.get('type', 'string')}{req}){desc_part}")
        return "\n".join(lines)

    def get_json(self) -> dict[str, Any]:
        """Return the OpenAI tool schema as a JSON-serializable dict.

        Returns:
            Full ``{"type": "function", "function": {...}}`` schema dict.
        """
        return self.to_openai_schema()

    def get_graphviz_fragment(self, ctx: GraphContext) -> GraphFragment:
        """Return a DOT node for this tool.

        The node uses a box shape with a green fill.  Also registers the node
        in the vis.js data via ``ctx.add_node()`` so that ``get_html()``
        produces a matching interactive node with a Markdown tooltip.

        Args:
            ctx: Mutable context for unique ID allocation and vis.js data.

        Returns:
            ``GraphFragment`` with one node statement and the node's ID as
            ``root_id``.
        """
        node_id = ctx.alloc_id(self.name)
        first_line = self.description.split("\n")[0][:80]
        stmt = _dot_node(
            node_id,
            label=f"[T] {self.name}",
            tooltip=first_line,
            shape="box",
            style="rounded,filled",
            fillcolor="honeydew",
            color="darkgreen",
        )
        # Cytoscape: label = concrete class name (rule: "shape title = class name")
        ctx.add_node(
            node_id,
            label=type(self).__name__,
            description_md=self.get_markdown(),
            node_class="tool",
        )
        return GraphFragment(dot_statements=[stmt], root_id=node_id)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"
