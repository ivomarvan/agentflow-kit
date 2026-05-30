"""Hotel booking demo — demonstrates domain events and custom GUI renderer.

The FakeLlmConnector simulates booking requests so no real LLM API key is needed.

Run with:
    uv run python examples/hotel_booking/hotel_booking_app.py          # run workflow
    uv run python examples/hotel_booking/hotel_booking_app.py -h       # help
    uv run python examples/hotel_booking/hotel_booking_app.py browser  # graph
    uv run python examples/hotel_booking/hotel_booking_app.py gui      # GUI server
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

from git_root_to_syspath import agr  # locate project root and add it to sys.path

agr()

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


class HotelBookingApp(AgentApp):
    """Hotel booking demo — shows domain events and custom GUI renderer.

    Uses FakeLlmConnector so no API key is required.
    The ReservationEvent emitted by HotelBookingTool is rendered as a table
    in the GUI when gui_renderers/hotel_reservation.vue is registered.
    """

    def __init__(self) -> None:
        super().__init__()
        self.connector = FakeLlmConnector()
        self._store = ReservationStore()
        self.registry = ToolRegistry([
            HotelBookingTool(store=self._store, event_bus=self.event_bus),
        ])
        self.graph = StateGraph(
            start=ProcessBooking,
            transitions=[
                Transition(ProcessBooking, StdSignal.ok, Done),
                Transition(Done, StdSignal.done, StdEnd),
            ],
        )

    @property
    def sample_prompts(self) -> list[str]:
        """Return demo prompts shown in the GUI prompt selector.

        Returns:
            List of example booking request strings.
        """
        return [
            "Book room 101 for John Smith from Dec 20 to Dec 23",
            "Reserve a double room for Mary Jones, Jan 5-8",
            "Book the penthouse for Bob Brown next weekend",
        ]

    async def run_workflow(self) -> str | None:
        """Run the hotel booking workflow and return a summary.

        Creates a fresh Context with the shared event_bus and tool registry,
        executes the StateGraph, and logs the total reservation count.

        Returns:
            Summary string with total reservation count and last booking result.
        """
        ctx = Context(
            connector=self.connector,
            tools=self.registry,
            event_bus=self.event_bus,
        )
        runner = StateGraphRunner(graph=self.graph, context=ctx)
        final = cast(HotelState, await runner.run(
            HotelState(request=self.current_prompt or "Book a room")
        ))
        total = len(self._store)
        logger.info("Reservations so far: %d", total)
        return (
            f"Booking complete. Total reservations: {total}. "
            f"Last: {final.last_booking_result}"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    HotelBookingApp().cli(__doc__, name=__name__)
