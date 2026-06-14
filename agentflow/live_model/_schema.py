"""JSON Schema builder for LiveModel @action method parameters."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Annotated, Any, Literal, get_args, get_origin, get_type_hints

from pydantic.fields import FieldInfo

_SUPPORTED_TYPES: dict[type, tuple[str, str]] = {
    str: ("string", "text"),
    int: ("integer", "number"),
    float: ("number", "number"),
    bool: ("boolean", "boolean"),
}


def _unwrap_optional(py_type: Any) -> Any:
    """Strip None from Optional / union types."""
    args = getattr(py_type, "__args__", None)
    if args and type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        return non_none[0] if non_none else str
    return py_type


def _resolve_annotation(hint: Any) -> tuple[Any, FieldInfo | None]:
    """Split Annotated[T, Field(...)] into base type and optional FieldInfo."""
    field_info: FieldInfo | None = None
    py_type = hint
    if get_origin(hint) is Annotated:
        args = get_args(hint)
        py_type = args[0]
        for meta in args[1:]:
            if isinstance(meta, FieldInfo):
                field_info = meta
    return _unwrap_optional(py_type), field_info


def _property_schema(py_type: Any, field_info: FieldInfo | None) -> dict[str, Any]:
    """Map a Python parameter type to a JSON Schema property dict."""
    origin = get_origin(py_type)
    if origin is Literal:
        enum_vals = list(get_args(py_type))
        prop: dict[str, Any] = {
            "type": "string",
            "enum": enum_vals,
            "x-widget": "select",
        }
    elif py_type not in _SUPPORTED_TYPES:
        raise TypeError(f"Unsupported @action parameter type: {py_type!r}")
    else:
        json_type, widget = _SUPPORTED_TYPES[py_type]
        prop = {"type": json_type, "x-widget": widget}

    if field_info is not None:
        if field_info.description:
            prop["description"] = field_info.description
        extra = field_info.json_schema_extra
        if isinstance(extra, dict):
            for key, value in extra.items():
                prop[key] = value
        for constraint in field_info.metadata:
            ge = getattr(constraint, "ge", None)
            le = getattr(constraint, "le", None)
            if ge is not None:
                prop["minimum"] = ge
            if le is not None:
                prop["maximum"] = le

    return prop


def build_action_parameters_schema(method: Callable[..., Any]) -> dict[str, Any]:
    """Build OpenAI-style parameters schema from an @action method signature."""
    try:
        hints = get_type_hints(method, include_extras=True)
    except Exception as exc:  # pragma: no cover
        raise TypeError(f"Cannot resolve type hints for {method.__name__}") from exc

    sig = inspect.signature(method)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        hint = hints.get(param_name, str)
        py_type, field_info = _resolve_annotation(hint)
        properties[param_name] = _property_schema(py_type, field_info)
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }
