"""SmartHomeModel — LiveModel for the smart-home example.

Run standalone:
    uv run python examples/agents/smart_home_model.py

Or use in AgentApp:
    from examples.agents.smart_home_model import SmartHomeModel
    app = AgentApp(live_model=SmartHomeModel(), ...)
"""

from __future__ import annotations

from git_root_to_syspath import agr  # noqa: E402

agr()

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from agentflow.gui.state_viewer import icon, room
from agentflow.live_model import LiveModel, action

_MAX_TEMP = 28.0


class KitchenState(BaseModel):
    """Kitchen room: temperature, lights, stove, and person count."""

    model_config = ConfigDict(frozen=False)

    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(20.0, title="Temperature")
    lights: Annotated[bool, icon("bulb", on_color="#fbbf24")] = Field(False, title="Lights")
    stove: Annotated[bool, icon("flame", on_color="#ef4444")] = Field(False, title="Stove")
    persons: Annotated[int, icon("person")] = Field(1, title="Persons")


class BedroomState(BaseModel):
    """Bedroom room: temperature, lights, person count."""

    model_config = ConfigDict(frozen=False)

    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(18.5, title="Temperature")
    lights: Annotated[bool, icon("bulb", on_color="#fbbf24")] = Field(True, title="Lights")
    persons: Annotated[int, icon("person")] = Field(0, title="Persons")


class LivingRoomState(BaseModel):
    """Living room: temperature, lights, person count."""

    model_config = ConfigDict(frozen=False)

    temperature: Annotated[float, icon("thermometer", unit="°C")] = Field(21.0, title="Temperature")
    lights: Annotated[bool, icon("bulb", on_color="#fbbf24")] = Field(True, title="Lights")
    persons: Annotated[int, icon("person")] = Field(2, title="Persons")


class HouseState(BaseModel):
    """Complete house state — drives the GUI Live State panel."""

    model_config = ConfigDict(frozen=False)

    kitchen: Annotated[KitchenState, room("Kitchen", col_span=2)] = Field(
        default_factory=KitchenState
    )
    bedroom: Annotated[BedroomState, room("Bedroom")] = Field(default_factory=BedroomState)
    living: Annotated[LivingRoomState, room("Living Room")] = Field(
        default_factory=LivingRoomState
    )


class SmartHomeModel(LiveModel):
    """Self-describing smart-home domain model with @action API."""

    def __init__(self) -> None:
        self._house = HouseState()

    @property
    def state(self) -> HouseState:
        return self._house

    def _room(self, room_name: str):
        room_state = getattr(self._house, room_name, None)
        if room_state is None:
            return None, f"Unknown room '{room_name}'. Available: kitchen, bedroom, living."
        return room_state, None

    @action
    def get_status(
        self,
        room: Annotated[
            str,
            Field(
                description="Room name: 'kitchen', 'bedroom', or 'living'.",
                json_schema_extra={
                    "x-widget": "select",
                    "enum": ["kitchen", "bedroom", "living"],
                },
            ),
        ],
    ) -> str:
        """Return current temperature, lights, and occupancy for the room."""
        room_state, err = self._room(room)
        if err:
            return err
        stove_part = (
            f", stove={'on' if room_state.stove else 'off'}"
            if isinstance(room_state, KitchenState)
            else ""
        )
        return (
            f"Room '{room}': temperature={room_state.temperature}°C, "
            f"lights={'on' if room_state.lights else 'off'}, "
            f"persons={room_state.persons}{stove_part}."
        )

    @action
    def set_temperature(
        self,
        room: Annotated[
            str,
            Field(
                description="Room name: 'kitchen', 'bedroom', or 'living'.",
                json_schema_extra={
                    "x-widget": "select",
                    "enum": ["kitchen", "bedroom", "living"],
                },
            ),
        ],
        celsius: Annotated[
            float,
            Field(
                description="Target temperature in °C (5–30).",
                ge=5.0,
                le=30.0,
                json_schema_extra={"x-widget": "number"},
            ),
        ],
    ) -> str:
        """Set the target temperature in the given room."""
        if celsius > _MAX_TEMP:
            return f"Temperature {celsius}°C exceeds safety limit of {_MAX_TEMP}°C. Not applied."
        room_state, err = self._room(room)
        if err:
            return err
        room_state.temperature = celsius
        return f"Temperature in '{room}' set to {celsius}°C."

    @action
    def toggle_light(
        self,
        room: Annotated[
            str,
            Field(
                description="Room name: 'kitchen', 'bedroom', or 'living'.",
                json_schema_extra={
                    "x-widget": "select",
                    "enum": ["kitchen", "bedroom", "living"],
                },
            ),
        ],
    ) -> str:
        """Toggle the light in the given room on or off."""
        room_state, err = self._room(room)
        if err:
            return err
        room_state.lights = not room_state.lights
        state = "on" if room_state.lights else "off"
        return f"Lights in '{room}' are now {state}."

    @action
    def toggle_stove(self) -> str:
        """Toggle the kitchen stove on or off."""
        kitchen = self._house.kitchen
        kitchen.stove = not kitchen.stove
        state = "on" if kitchen.stove else "off"
        return f"Kitchen stove is now {state}."

    @action
    def set_persons(
        self,
        room: Annotated[
            str,
            Field(
                description="Room name: 'kitchen', 'bedroom', or 'living'.",
                json_schema_extra={
                    "x-widget": "select",
                    "enum": ["kitchen", "bedroom", "living"],
                },
            ),
        ],
        count: Annotated[
            int,
            Field(
                description="Number of persons in the room (0–10).",
                ge=0,
                le=10,
                json_schema_extra={"x-widget": "number"},
            ),
        ],
    ) -> str:
        """Set the number of persons in a room."""
        room_state, err = self._room(room)
        if err:
            return err
        room_state.persons = count
        return f"Persons in '{room}' set to {count}."


if __name__ == "__main__":
    SmartHomeModel.demo()
