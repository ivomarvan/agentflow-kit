"""Hotel Booking Voice Assistant — Emma at the Four Colours Hotel.

Multi-turn booking workflow with hub-and-spoke data collection, conflict
detection, confirmation guards, and a Live State hotel guest book panel.
"""

# Run:
#     uv run python examples/hotel_booking/hotel_booking_app.py -h
#     uv run python examples/hotel_booking/hotel_booking_app.py run
#     uv run python examples/hotel_booking/hotel_booking_app.py gui
#     uv run python examples/hotel_booking/hotel_booking_app.py graph --browser

from __future__ import annotations

from git_root_to_syspath import agr  # noqa: E402

agr()

from agentflow import AgentApp  # noqa: E402
from agentflow.llm.cache import LlmFileCache  # noqa: E402
from agentflow.llm.LlmPool import LlmPool  # noqa: E402
from agentflow.statemachine import Context, StateGraph, StdEnd, Transition  # noqa: E402
from agentflow.tools.ToolRegistry import ToolRegistry  # noqa: E402
from examples.projects.hotel_booking.booking_store import _STORE  # noqa: E402
from examples.projects.hotel_booking.live_state import _HOTEL  # noqa: E402
from examples.projects.hotel_booking.state import HotelSignal, HotelState  # noqa: E402
from examples.projects.hotel_booking.tools import (  # noqa: E402
    CalculatePriceTool,
    CancelReservationTool,
    CheckAvailabilityTool,
    CreateReservationTool,
    FindAlternativesTool,
    FindReservationTool,
    GetRoomDetailsTool,
)
from examples.projects.hotel_booking.vertices import (  # noqa: E402
    AlternativesVertex,
    AskCapacityVertex,
    AskDatesVertex,
    AskGuestNameVertex,
    AvailabilityCheckerVertex,
    BookingExecutorVertex,
    CancellationFlowVertex,
    ConfirmationVertex,
    DataDispatcherVertex,
    InquiryVertex,
    IntentParserVertex,
    OtherHandlerVertex,
    VoiceFormatterVertex,
)

_DEFAULT_QUESTION = "I'd like to make a room reservation."

_SYSTEM_PROMPT = (
    "You are Emma, a virtual receptionist at the Four Colours Hotel. "
    "Help guests book rooms, cancel reservations, and answer room questions."
)

_TOOLS = [
    CheckAvailabilityTool(_STORE),
    GetRoomDetailsTool(_STORE),
    CalculatePriceTool(_STORE),
    CreateReservationTool(_STORE),
    CancelReservationTool(_STORE),
    FindReservationTool(_STORE),
    FindAlternativesTool(_STORE),
]

_registry = ToolRegistry(_TOOLS)

if __name__ == "__main__":
    _app = AgentApp(
        doc=__doc__,
        system_prompt=_SYSTEM_PROMPT,
        default_question=_DEFAULT_QUESTION,
        sample_prompts=[
            "Book a room for two from July 20 to 22 for Smith.",
            "Book the Blue Room from July 8 to 10 for Brown.",
            "Cancel the reservation for Novak family arriving July 10.",
            "How much is the Red Room per night?",
            "What's the weather today?",
        ],
        initial_state_factory=lambda q: HotelState(
            messages=(
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": q},
            ),
        ),
        context=Context(
            pool=LlmPool(cache=LlmFileCache(__file__)),
            tool_registries={"default": _registry},
        ),
        live_state=_HOTEL,
        state_graph=StateGraph(
            start=IntentParserVertex,
            initialized_vertexes=[
                IntentParserVertex(),
                DataDispatcherVertex(),
                AskGuestNameVertex(),
                AskDatesVertex(),
                AskCapacityVertex(),
                AvailabilityCheckerVertex(max_rounds=4),
                AlternativesVertex(max_rounds=4),
                ConfirmationVertex(),
                BookingExecutorVertex(),
                CancellationFlowVertex(max_rounds=6),
                InquiryVertex(max_rounds=4),
                OtherHandlerVertex(),
                VoiceFormatterVertex(),
            ],
            transitions=[
                Transition(IntentParserVertex, HotelSignal.intent_new, DataDispatcherVertex),
                Transition(IntentParserVertex, HotelSignal.intent_cancel, CancellationFlowVertex),
                Transition(IntentParserVertex, HotelSignal.intent_inquiry, InquiryVertex),
                Transition(IntentParserVertex, HotelSignal.intent_other, OtherHandlerVertex),
                Transition(DataDispatcherVertex, HotelSignal.need_name, AskGuestNameVertex),
                Transition(DataDispatcherVertex, HotelSignal.need_dates, AskDatesVertex),
                Transition(DataDispatcherVertex, HotelSignal.need_capacity, AskCapacityVertex),
                Transition(
                    DataDispatcherVertex, HotelSignal.data_complete, AvailabilityCheckerVertex
                ),
                Transition(AskGuestNameVertex, HotelSignal.name_collected, DataDispatcherVertex),
                Transition(AskDatesVertex, HotelSignal.dates_collected, DataDispatcherVertex),
                Transition(AskCapacityVertex, HotelSignal.capacity_collected, DataDispatcherVertex),
                Transition(
                    AvailabilityCheckerVertex, HotelSignal.available, ConfirmationVertex
                ),
                Transition(
                    AvailabilityCheckerVertex, HotelSignal.unavailable, AlternativesVertex
                ),
                Transition(AlternativesVertex, HotelSignal.alternatives_ok, ConfirmationVertex),
                Transition(AlternativesVertex, HotelSignal.declined, StdEnd),
                Transition(ConfirmationVertex, HotelSignal.confirmed, BookingExecutorVertex),
                Transition(ConfirmationVertex, HotelSignal.declined, StdEnd),
                Transition(BookingExecutorVertex, HotelSignal.done, VoiceFormatterVertex),
                Transition(CancellationFlowVertex, HotelSignal.done, VoiceFormatterVertex),
                Transition(CancellationFlowVertex, HotelSignal.declined, StdEnd),
                Transition(InquiryVertex, HotelSignal.done, StdEnd),
                Transition(OtherHandlerVertex, HotelSignal.reminder_sent, IntentParserVertex),
                Transition(OtherHandlerVertex, HotelSignal.done, StdEnd),
                Transition(VoiceFormatterVertex, HotelSignal.done, StdEnd),
            ],
        ),
    )

    _app.cli(__doc__, name=__name__)
