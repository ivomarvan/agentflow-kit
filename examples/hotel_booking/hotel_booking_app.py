"""Hotel booking demo — demonstrates domain events and custom GUI renderer.

The FakeLlmConnector simulates booking requests so no real LLM API key is needed.
"""

# Run:
#     uv run python examples/hotel_booking/hotel_booking_app.py -h       # help
#     uv run python examples/hotel_booking/hotel_booking_app.py run      # run workflow
#     uv run python examples/hotel_booking/hotel_booking_app.py graph --browser
#     uv run python examples/hotel_booking/hotel_booking_app.py gui      # GUI server

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

from git_root_to_syspath import agr  # locate project root and add it to sys.path

agr()

from agentflow.logging_config import setup_pretty_logging  # noqa: E402
from agentflow import AgentApp  # noqa: E402
from agentflow.statemachine import (  # noqa: E402
    Context,
    StateGraph,
    StateGraphRunner,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from agentflow.statemachine.testing import FakeLlmConnector  # noqa: E402
from agentflow.tools.ToolRegistry import ToolRegistry  # noqa: E402
from examples.hotel_booking.hotel_booking_tool import HotelBookingTool  # noqa: E402
from examples.hotel_booking.reservation_store import ReservationStore  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HotelState:
    """Immutable state for the hotel booking workflow.

    Attributes:
        request: The incoming booking request text.
        last_booking_result: Result string from the most recent booking.
    """

    request: str = ""
    last_booking_result: str = ""


@dataclass
class HotelPatch:
    """Mutable patch applied to HotelState after each super-step.

    A field set to None means "do not overwrite" in the state reducer.

    Attributes:
        request: Optional new request string.
        last_booking_result: Optional new booking result string.
    """

    request: str | None = None
    last_booking_result: str | None = None


class ProcessBooking(StateVertex):
    """Processes a booking request using the HotelBookingTool via EventBus."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:  # type: ignore[override]
        """Call HotelBookingTool.run() with a demo booking and emit a ReservationEvent.

        Args:
            state: Current HotelState snapshot.
            ctx: Shared context; ctx.tools must contain HotelBookingTool.

        Returns:
            (StdSignal.ok, HotelPatch) with last_booking_result set.
        """
        s = cast(HotelState, state)
        if ctx.tools is None:
            return StdSignal.ok, HotelPatch(last_booking_result="No tool registry available.")

        tool = ctx.tools.get("book_hotel_room")
        if tool is None:
            return StdSignal.ok, HotelPatch(last_booking_result="HotelBookingTool not found.")

        booking_tool = cast(HotelBookingTool, tool)
        result = await booking_tool.run(
            guest_name="John Smith",
            room="101",
            check_in="2024-12-20",
            check_out="2024-12-23",
        )
        logger.info("Booking processed: request=%r result=%r", s.request, result)
        return StdSignal.ok, HotelPatch(last_booking_result=result)


class Done(StateVertex):
    """Terminal vertex — signals workflow completion."""

    async def run(self, state: object, ctx: Context) -> tuple[Any, Any]:  # type: ignore[override]
        """Signal that the workflow is done.

        Args:
            state: Current HotelState snapshot (not modified).
            ctx: Shared context (not used).

        Returns:
            (StdSignal.done, empty HotelPatch).
        """
        return StdSignal.done, HotelPatch()


_store = ReservationStore()
_graph = StateGraph(
    start=ProcessBooking,
    transitions=[
        Transition(ProcessBooking, StdSignal.ok, Done),
        Transition(Done, StdSignal.done, StdEnd),
    ],
)

_app = AgentApp(
    doc=__doc__,
    sample_prompts=[
        "Book room 101 for John Smith from Dec 20 to Dec 23",
        "Reserve a double room for Mary Jones, Jan 5-8",
        "Book the penthouse for Bob Brown next weekend",
    ],
    state_graph=_graph,
    initial_state_factory=lambda q: HotelState(request=q or "Book a room"),
    context=Context(),
)

_registry = ToolRegistry([
    HotelBookingTool(store=_store, event_bus=_app.event_bus),
])
_app._context = Context(
    tool_registries={"default": _registry},
    event_bus=_app.event_bus,
)
_app.context = _app._context


def _extract_hotel_result(state: HotelState) -> str | None:
    total = len(_store)
    logger.info("Reservations so far: %d", total)
    return (
        f"Booking complete. Total reservations: {total}. "
        f"Last: {state.last_booking_result}"
    )


_app._extract_result = _extract_hotel_result  # type: ignore[method-assign]

if __name__ == "__main__":
    setup_pretty_logging()
    _app.cli(__doc__, name=__name__)
