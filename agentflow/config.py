"""Configuration introspection utilities for AgentApp GUI integration.

Provides ConfigParam — a lightweight descriptor for a single configurable
parameter — used by get_config_schema() / get_config() / set_config() on
AgentApp to expose runtime-editable parameters to the GUI settings panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfigParam:
    """Metadata describing a single configurable parameter.

    Used by AgentApp.get_config_schema() / get_config() / set_config() to
    expose a uniform parameter-inspection API regardless of the underlying
    implementation (Pydantic model, plain attribute, etc.).

    Attributes:
        name: Parameter name as used in dot-path notation (e.g. 'model').
        type_hint: String representation of the type, e.g. 'str', 'float'.
        value: Current runtime value of the parameter.
        description: Human-readable description for the GUI tooltip.
        min_value: Optional minimum bound for numeric parameters.
        max_value: Optional maximum bound for numeric parameters.
        choices: Optional list of allowed values (for enum / Literal types).
        required: True when the parameter must be set before the app can run.
    """

    name: str
    type_hint: str
    value: Any
    description: str = ""
    min_value: float | None = None
    max_value: float | None = None
    choices: list[Any] = field(default_factory=list)
    required: bool = False
