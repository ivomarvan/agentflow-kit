"""CounterModel — minimal LiveModel example.

Demonstrates:
- Defining a LiveModel with @action methods
- Pydantic live state (CounterState)
- x-widget hints for parameter inputs
- Standalone demo mode

Run:
    uv run python examples/framework/05_counter_live_model.py

Then open http://127.0.0.1:8765/demo to interact with the counter.
"""

from __future__ import annotations

from git_root_to_syspath import agr  # noqa: E402

agr()

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from agentflow.live_model import LiveModel, action


class CounterState(BaseModel):
    """Live state for the counter demo."""

    model_config = ConfigDict(frozen=False)
    count: int = 0
    history: list[str] = Field(default_factory=list)


class CounterModel(LiveModel):
    """Simple counter with increment, decrement, reset, and set_value actions."""

    _MAX_HISTORY = 5

    def __init__(self) -> None:
        self._state = CounterState()

    @property
    def state(self) -> CounterState:
        return self._state

    def _record(self, note: str) -> None:
        self._state.history.append(note)
        if len(self._state.history) > self._MAX_HISTORY:
            self._state.history.pop(0)

    @action
    def increment(
        self,
        step: Annotated[
            int,
            Field(
                description="Amount to add (1–100).",
                ge=1,
                le=100,
                json_schema_extra={"x-widget": "number"},
            ),
        ] = 1,
    ) -> str:
        """Add step to the counter."""
        self._state.count += step
        self._record(f"+{step} → {self._state.count}")
        return f"Counter is now {self._state.count}."

    @action
    def decrement(
        self,
        step: Annotated[
            int,
            Field(
                description="Amount to subtract (1–100).",
                ge=1,
                le=100,
                json_schema_extra={"x-widget": "number"},
            ),
        ] = 1,
    ) -> str:
        """Subtract step from the counter (minimum 0)."""
        self._state.count = max(0, self._state.count - step)
        self._record(f"-{step} → {self._state.count}")
        return f"Counter is now {self._state.count}."

    @action
    def reset(self) -> str:
        """Reset the counter to zero and clear history."""
        self._state.count = 0
        self._state.history.clear()
        return "Counter reset to zero."

    @action
    def set_value(
        self,
        value: Annotated[
            int,
            Field(
                description="New counter value (0–9999).",
                ge=0,
                le=9999,
                json_schema_extra={"x-widget": "number"},
            ),
        ],
    ) -> str:
        """Set the counter to an explicit value."""
        self._state.count = value
        self._record(f"set={value}")
        return f"Counter set to {value}."


if __name__ == "__main__":
    CounterModel.demo()
