"""Live state viewer — display metadata DSL for GUI visualisation.

Provides annotation helpers (``icon``, ``room``, ``panel``) that attach display
hints to Pydantic ``BaseModel`` fields.  The GUI reads these hints to render a
live widget showing the application's world state (e.g. smart-home room layout,
hotel room occupancy) while an agent is running.

Usage::

    from pydantic import BaseModel, Field
    from typing import Annotated
    from agentflow.gui.state_viewer import icon, room, extract_display_schema

    class KitchenState(BaseModel):
        temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(
            20.0, title="Teplota"
        )
        lights:  Annotated[bool, icon("bulb",  on_color="#fbbf24")] = Field(
            False, title="Světla"
        )
        stove:   Annotated[bool, icon("flame", on_color="#ef4444")] = Field(
            False, title="Sporák"
        )
        persons: Annotated[int, icon("person")] = Field(1, title="Osoby")

    class HouseState(BaseModel):
        kuchyne: Annotated[KitchenState, room("Kuchyně", col_span=2)] = Field(
            default_factory=KitchenState
        )

    schema = extract_display_schema(HouseState)
    # → {field_name: {title, type, display, room_hint, nested_schema, ...}, ...}

Supported icon names (map to emoji in the GUI):
  bulb, thermometer, flame, person, snowflake, lock, door, tv, bell, wifi,
  plug, fan, sun, moon, water, car, clock, star, check, calendar
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

# ---------------------------------------------------------------------------
# Hint marker classes — frozen so they can live inside Annotated
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IconHint:
    """Display hint: render a scalar field as a coloured icon + value.

    Attributes:
        name:      Icon identifier (e.g. ``"bulb"``, ``"thermometer"``).
        on_color:  CSS colour when value is truthy or positive.
        off_color: CSS colour when value is falsy or zero.
        unit:      Suffix appended to numeric values (e.g. ``"°C"``).
    """

    name: str
    on_color: str = "#22c55e"
    off_color: str = "#94a3b8"
    unit: str = ""


@dataclass(frozen=True)
class RoomHint:
    """Display hint: render a nested model as a labelled room box in the grid.

    Attributes:
        label:    Human-readable room name shown in the box header.
        col_span: Number of grid columns the room occupies (1 = narrow, 2 = wide).
    """

    label: str
    col_span: int = 1


@dataclass(frozen=True)
class PanelHint:
    """Display hint: wrap a nested list/object in a labelled container panel.

    Attributes:
        label:  Container header label.
        layout: Layout variant — ``"grid"``, ``"list"``, or ``"timeline"``.
    """

    label: str
    layout: str = "grid"


# ---------------------------------------------------------------------------
# Factory helpers — the public API
# ---------------------------------------------------------------------------

def icon(
    name: str,
    *,
    on_color: str = "#22c55e",
    off_color: str = "#94a3b8",
    unit: str = "",
) -> IconHint:
    """Return an ``IconHint`` annotation for a scalar field.

    Attach as ``Annotated[type, icon(...)]`` on a Pydantic model field.

    Args:
        name:      Icon key — one of: ``bulb``, ``thermometer``, ``flame``,
                   ``person``, ``snowflake``, ``lock``, ``door``, ``tv``,
                   ``bell``, ``wifi``, ``plug``, ``fan``, ``sun``, ``moon``,
                   ``water``, ``car``, ``clock``, ``star``, ``check``.
        on_color:  CSS colour when value is ``True`` / positive.
        off_color: CSS colour when value is ``False`` / zero.
        unit:      Suffix for numeric fields (e.g. ``"°C"``, ``"kWh"``).

    Returns:
        ``IconHint`` to use inside ``Annotated[...]``.
    """
    return IconHint(name, on_color, off_color, unit)


def room(label: str, *, col_span: int = 1) -> RoomHint:
    """Return a ``RoomHint`` annotation for a nested ``BaseModel`` field.

    Args:
        label:    Display name shown in the room box header.
        col_span: Grid column span (1 = normal, 2 = wide).

    Returns:
        ``RoomHint`` to use inside ``Annotated[RoomState, room("Kitchen")]``.
    """
    return RoomHint(label, col_span)


def panel(label: str, *, layout: str = "grid") -> PanelHint:
    """Return a ``PanelHint`` annotation for a nested list or model field.

    Args:
        label:  Container header label.
        layout: ``"grid"`` | ``"list"`` | ``"timeline"``.

    Returns:
        ``PanelHint`` to use inside ``Annotated[list[Item], panel("Bookings")]``.
    """
    return PanelHint(label, layout)


# ---------------------------------------------------------------------------
# Schema extractor
# ---------------------------------------------------------------------------

def extract_display_schema(model_class: type[BaseModel]) -> dict[str, Any]:
    """Build a JSON-serialisable display schema from a Pydantic ``BaseModel`` class.

    Walks all annotated type hints and collects ``IconHint``, ``RoomHint``, and
    ``PanelHint`` metadata together with Pydantic ``FieldInfo`` title/description.
    The resulting dict is sent to the frontend as part of ``StateUpdateEvent``
    and consumed by the ``StateViewerPanel`` component.

    Args:
        model_class: A Pydantic ``BaseModel`` subclass with optional display annotations.

    Returns:
        Dict ``{field_name: field_schema}`` where each ``field_schema`` contains:
        ``title``, ``type`` (``"float"``|``"int"``|``"bool"``|``"str"``|``"object"``|
        ``"list"``), ``display`` (optional icon dict), ``room_hint`` (optional),
        ``panel_hint`` (optional), ``nested_schema`` (optional, for object fields).
    """
    try:
        hints = typing.get_type_hints(model_class, include_extras=True)
    except Exception:
        return {}

    schema: dict[str, Any] = {}

    for field_name, hint in hints.items():
        if field_name.startswith("_") or field_name == "model_config":
            continue

        entry: dict[str, Any] = {}

        # Unwrap Annotated[base_type, *metadata]
        base_type: Any = hint
        if hasattr(hint, "__metadata__"):
            base_type = hint.__args__[0]
            for meta in hint.__metadata__:
                if isinstance(meta, FieldInfo):
                    if meta.title:
                        entry["title"] = meta.title
                    if meta.description:
                        entry["description"] = meta.description
                elif isinstance(meta, IconHint):
                    entry["display"] = {
                        "type": "icon",
                        "icon": meta.name,
                        "on_color": meta.on_color,
                        "off_color": meta.off_color,
                        "unit": meta.unit,
                    }
                elif isinstance(meta, RoomHint):
                    entry["room_hint"] = {
                        "label": meta.label,
                        "col_span": meta.col_span,
                    }
                elif isinstance(meta, PanelHint):
                    entry["panel_hint"] = {
                        "label": meta.label,
                        "layout": meta.layout,
                    }

        # Complement title/description from Pydantic model_fields
        if hasattr(model_class, "model_fields") and field_name in model_class.model_fields:
            pf = model_class.model_fields[field_name]
            if pf.title and "title" not in entry:
                entry["title"] = pf.title
            if pf.description and "description" not in entry:
                entry["description"] = pf.description

        # Determine Python type string
        entry["type"] = _type_name(base_type)

        # Recurse into nested BaseModel
        if isinstance(base_type, type) and issubclass(base_type, BaseModel):
            entry["type"] = "object"
            entry["nested_schema"] = extract_display_schema(base_type)

        schema[field_name] = entry

    return schema


def _type_name(t: Any) -> str:
    """Return a simple type name string for the display schema.

    Args:
        t: Python type object.

    Returns:
        One of: ``"float"``, ``"int"``, ``"bool"``, ``"str"``, ``"list"``,
        ``"object"``, ``"unknown"``.
    """
    if t is float:
        return "float"
    if t is int:
        return "int"
    if t is bool:
        return "bool"
    if t is str:
        return "str"
    origin = typing.get_origin(t)
    if origin is list:
        return "list"
    if isinstance(t, type) and issubclass(t, BaseModel):
        return "object"
    return "unknown"
