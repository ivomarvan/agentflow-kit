"""Hotel Booking — agentflow application

A voice assistant for a fictional Four Colours Hotel.
The guest (via ASR input) can book a room, cancel a reservation,
or ask about room availability and pricing.  Emma (the AI receptionist)
always responds in Czech.

Architecture:
    Every turn starts at OrderDirectionVertex (intent router).
    When flow == 'initial' an LLM call detects intent and routes to the
    appropriate data-collection vertex.  Subsequent turns short-circuit
    directly without the intent-detection call.
    Data collection (booking / cancellation) uses pydantic.create_model()
    to build a schema with only the still-missing fields each turn.
    AvailabilityVertex, ExecuteBookingVertex, ExecuteCancellationVertex are
    pure StateVertex nodes (no LLM) that call BookingStore directly.

Run:
    uv run python examples/projects/hotel_booking/hotel_booking_app.py run "Hello"
    uv run python examples/projects/hotel_booking/hotel_booking_app.py gui
    uv run python examples/projects/hotel_booking/hotel_booking_app.py graph --browser
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to sys.path so the package is importable regardless of
# which directory the script is invoked from.
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentflow import AgentApp
from agentflow.llm.LlmPool import LlmPool
from agentflow.logging_config import setup_pretty_logging
from agentflow.statemachine import (
    Context,
    StateGraph,
    StateGraphRunner,
    StdEnd,
    Transition,
)
from agentflow.tools.ToolRegistry import ToolRegistry

from hotel_booking.booking_store import BookingStore
from hotel_booking.hotel_booking_model import HotelBookingModel, install_hotel_model
from hotel_booking.state import HotelBookingSignal, HotelBookingState, Order, initial_state

from hotel_booking.tools import (
    CalculatePriceTool,
    CancelReservationTool,
    CheckAvailabilityTool,
    CreateReservationTool,
    FindAlternativesTool,
    FindReservationTool,
    GetRoomDetailsTool,
)

from hotel_booking.vertices.order_direction_vertex import OrderDirectionVertex
from hotel_booking.vertices.order_details_vertex import OrderDetailsVertex
from hotel_booking.vertices.cancellation_details_vertex import CancellationDetailsVertex
from hotel_booking.vertices.inquiry_vertex import InquiryVertex
from hotel_booking.vertices.other_handler_vertex import OtherHandlerVertex
from hotel_booking.vertices.availability_vertex import AvailabilityVertex
from hotel_booking.vertices.order_confirmation_vertex import OrderConfirmationVertex
from hotel_booking.vertices.execute_booking_vertex import ExecuteBookingVertex
from hotel_booking.vertices.execute_cancellation_vertex import ExecuteCancellationVertex


# ---------------------------------------------------------------------------
# Graph topology
# ---------------------------------------------------------------------------

def build_graph(store: BookingStore) -> StateGraph:
    """Assemble and return the Hotel Booking StateGraph.

    Graph summary:
        OrderDirectionVertex
          ├─[order_request]         → OrderDetailsVertex
          ├─[order_cancellation]    → CancellationDetailsVertex
          ├─[order_inquiry]         → InquiryVertex
          ├─[order_other]           → OtherHandlerVertex
          ├─[awaiting_confirmation] → OrderConfirmationVertex
          └─[need_more_data]        → StdEnd

        OrderDetailsVertex
          ├─[data_complete]  → AvailabilityVertex
          ├─[order_other]    → OtherHandlerVertex
          ├─[order_inquiry]  → InquiryVertex
          └─[need_more_data] → StdEnd

        CancellationDetailsVertex
          ├─[data_complete]  → ExecuteCancellationVertex
          ├─[order_other]    → OtherHandlerVertex
          └─[need_more_data] → StdEnd

        AvailabilityVertex
          ├─[available]    → OrderConfirmationVertex
          └─[unavailable]  → StdEnd

        OrderConfirmationVertex
          ├─[confirmed]      → ExecuteBookingVertex
          ├─[declined]       → StdEnd
          └─[need_more_data] → StdEnd

        ExecuteBookingVertex     → [done / fail] → StdEnd
        ExecuteCancellationVertex → [done / fail] → StdEnd
        InquiryVertex             → [done]        → StdEnd
        OtherHandlerVertex        → [done]        → StdEnd

    Args:
        store: BookingStore injected into StateVertex nodes that need it.

    Returns:
        Configured StateGraph ready for use in AgentApp.
    """
    direction_v      = OrderDirectionVertex()
    details_v        = OrderDetailsVertex()
    cancellation_v   = CancellationDetailsVertex()
    inquiry_v        = InquiryVertex()
    other_v          = OtherHandlerVertex()
    availability_v   = AvailabilityVertex(store=store)
    confirmation_v   = OrderConfirmationVertex()
    exec_booking_v   = ExecuteBookingVertex(store=store)
    exec_cancel_v    = ExecuteCancellationVertex(store=store)
    end              = StdEnd()

    S = HotelBookingSignal  # alias for readability

    return StateGraph(
        start=direction_v,
        transitions=[
            # --- OrderDirectionVertex ---
            Transition(direction_v, S.order_request,         details_v),
            Transition(direction_v, S.order_cancellation,    cancellation_v),
            Transition(direction_v, S.order_inquiry,         inquiry_v),
            Transition(direction_v, S.order_other,           other_v),
            Transition(direction_v, S.awaiting_confirmation, confirmation_v),
            Transition(direction_v, S.need_more_data,        end),

            # --- OrderDetailsVertex ---
            Transition(details_v, S.data_complete,   availability_v),
            Transition(details_v, S.order_other,     other_v),
            Transition(details_v, S.order_inquiry,   inquiry_v),
            Transition(details_v, S.need_more_data,  end),

            # --- CancellationDetailsVertex ---
            Transition(cancellation_v, S.data_complete,  exec_cancel_v),
            Transition(cancellation_v, S.order_other,    other_v),
            Transition(cancellation_v, S.need_more_data, end),

            # --- AvailabilityVertex ---
            Transition(availability_v, S.available,   confirmation_v),
            Transition(availability_v, S.unavailable, end),

            # --- OrderConfirmationVertex ---
            Transition(confirmation_v, S.confirmed,      exec_booking_v),
            Transition(confirmation_v, S.declined,       end),
            Transition(confirmation_v, S.need_more_data, end),

            # --- Terminal StateVertices ---
            Transition(exec_booking_v,  S.done, end),
            Transition(exec_booking_v,  S.fail, end),
            Transition(exec_cancel_v,   S.done, end),
            Transition(exec_cancel_v,   S.fail, end),
            Transition(inquiry_v,       S.done, end),
            Transition(other_v,         S.done, end),
        ],
    )


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def build_registry(model: HotelBookingModel) -> ToolRegistry:
    """Build the ToolRegistry wired to the model's booking store.

    All tools operate on the same BookingStore / HotelBookState instance
    that the GUI LiveModel observes, so tool actions appear in the Guest Book.

    Args:
        model: Live model whose store the tools will operate on.

    Returns:
        ToolRegistry with all hotel booking tools.
    """
    store = model._store  # noqa: SLF001
    return ToolRegistry([
        CheckAvailabilityTool(store),
        GetRoomDetailsTool(store),
        CalculatePriceTool(store),
        CreateReservationTool(store),
        CancelReservationTool(store),
        FindReservationTool(store),
        FindAlternativesTool(store),
    ])


# ---------------------------------------------------------------------------
# Application — subclass AgentApp to maintain state across turns
# ---------------------------------------------------------------------------

class HotelBookingApp(AgentApp):
    """AgentApp subclass that accumulates conversation state across turns.

    The base AgentApp creates a fresh initial state for every turn via
    initial_state_factory.  For a multi-turn voicebot we need the order,
    flow, and message history to persist.  HotelBookingApp overrides
    run_workflow() to carry forward state.messages, state.order, and
    state.flow from the previous turn.
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._session_state: HotelBookingState | None = None

    async def run_workflow(self) -> str | None:
        """Execute one conversation turn with accumulated state.

        Builds the initial state by appending the new user message to the
        previous turn's accumulated state (messages + order + flow).
        Stores the final state for the next turn.

        Returns:
            TTS-ready response string for the guest, or None.
        """
        from agentflow.statemachine.context import Context as _Context

        ctx = _Context(
            pool=self._context.pool,
            tool_registries=self._merge_tool_registries(),
            tools=self._context.tools,
            event_bus=self.event_bus,
            live_state=self._live_state,
        )
        self._last_ctx = ctx

        new_msg = {"role": "user", "content": self.current_prompt}

        if self._session_state is None:
            current_initial = HotelBookingState(messages=(new_msg,))
        else:
            current_initial = HotelBookingState(
                messages=self._session_state.messages + (new_msg,),
                order=self._session_state.order,
                flow=self._session_state.flow,
            )

        runner = StateGraphRunner(self._state_graph, ctx)
        final_state = await runner.run(current_initial)
        self._session_state = final_state
        return self._extract_result(final_state)


# ---------------------------------------------------------------------------
# Module-level wiring
# ---------------------------------------------------------------------------

# Configure logging before building the graph so topology warnings are visible.
setup_pretty_logging()

_SAMPLE_PROMPTS = [
    "Hi, I'm Gorge and I would like to book the red room with you for July 15-18. this year",
    "Dobrý den, chtěl bych rezervovat pokoj na příští týden.",
    "Hello, I'd like to book a room for two people from July 15 to 18.",
    "Chtěl bych zrušit svou rezervaci.",
    "Jaké pokoje máte k dispozici?",
    "Kolik stojí červený pokoj na víkend?",
]

_MODEL = install_hotel_model()

_APP = HotelBookingApp(
    doc=__doc__,
    context=Context(
        pool=LlmPool(),
        tool_registries={"default": build_registry(_MODEL)},
    ),
    state_graph=build_graph(_MODEL._store),  # noqa: SLF001
    initial_state_factory=lambda q: initial_state(q),  # only used for first turn
    live_model=_MODEL,
    sample_prompts=_SAMPLE_PROMPTS,
)


if __name__ == "__main__":
    _APP.cli(__doc__, name=__name__)
