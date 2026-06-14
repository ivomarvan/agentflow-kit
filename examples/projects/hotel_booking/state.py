"""State, patch, and routing signals for Hotel Booking.

State:  frozen dataclass — immutable snapshot passed between vertices.
Patch:  mutable dataclass — vertices return (signal, patch); the runner
        merges patches into a new state via apply_patches().
Signal: Enum — determines which transition to follow after each vertex.

Conversation flow (high-level):
    Every turn the graph starts at OrderDirectionVertex.
    When flow == "initial" the LLM detects intent and sets flow to "booking",
    "cancellation", or stays "initial" until the intent is clear.
    When flow != "initial" OrderDirectionVertex short-circuits (no LLM call)
    and routes directly to the appropriate data-collection vertex.
    After data_complete the graph checks availability, collects confirmation,
    and executes the booking or cancellation via a StateVertex (no LLM).
"""

from __future__ import annotations

import dataclasses
import operator
from dataclasses import dataclass, field
from enum import auto
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentflow.statemachine import Signal, UNSET


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class HotelBookingSignal(Signal):
    """Routing signals emitted by Hotel Booking vertices."""

    order_request          = auto()   # → OrderDetailsVertex (new booking flow)
    order_cancellation     = auto()   # → CancellationDetailsVertex
    order_inquiry          = auto()   # → InquiryVertex (room info questions)
    order_other            = auto()   # → OtherHandlerVertex (off-topic)
    awaiting_confirmation  = auto()   # → OrderConfirmationVertex (from direction when flow='awaiting_confirmation')
    need_more_data         = auto()   # → StdEnd (wait for next user turn)
    data_complete          = auto()   # → AvailabilityVertex / ExecuteCancellationVertex
    available              = auto()   # → OrderConfirmationVertex
    unavailable            = auto()   # → StdEnd (inform user; alternatives to be added later)
    confirmed              = auto()   # → ExecuteBookingVertex
    declined               = auto()   # → StdEnd
    done                   = auto()   # → StdEnd (operation completed)
    fail                   = auto()   # → StdEnd (unrecoverable error)


# ---------------------------------------------------------------------------
# Order  (Pydantic — schema used for prompt generation and validation)
# ---------------------------------------------------------------------------

class Order(BaseModel):
    """Current booking or cancellation transaction, accumulated across conversation turns.

    Fields that are LLM-extracted (guest provides them) remain empty strings / zero
    until provided.  Fields that are system-computed (total_price, reservation_id)
    are set by StateVertex tool calls after data_complete.
    Use with_update() for targeted field changes — returns a new immutable instance.

    Lifecycle:
        - Created fresh at conversation start.
        - action set by OrderDirectionVertex.
        - Remaining booking fields filled by OrderDetailsVertex loop.
        - total_price set by AvailabilityVertex after availability check.
        - reservation_id set by ExecuteBookingVertex after confirmed booking.
        - Reset to Order() after a completed or declined transaction.
    """

    model_config = ConfigDict(frozen=True)

    action: Literal["NEW_BOOKING", "CANCELLATION", ""] = Field(
        default="", description="Guest intent: NEW_BOOKING or CANCELLATION."
    )
    guest_name: str = Field(default="", description="Full name of the guest.")
    check_in: str = Field(default="", description="Check-in date (YYYY-MM-DD).")
    check_out: str = Field(default="", description="Check-out date (YYYY-MM-DD).")
    capacity: int = Field(default=0, description="Number of guests (1–3).", ge=0, le=3)
    selected_room_id: str = Field(
        default="",
        description="Room ID: 'red', 'blue', 'green', or 'white'.",
        json_schema_extra={"enum": ["red", "blue", "green", "white", ""]},
    )
    # System-computed fields — NOT extracted by the LLM; set by StateVertex tool calls.
    total_price: float = Field(default=0.0, description="Computed total price in EUR (set by system).")
    reservation_id: str = Field(default="", description="UUID assigned after confirmed booking (set by system).")

    def with_update(self, **kwargs: Any) -> "Order":
        """Return a new Order with the specified fields replaced."""
        return self.model_copy(update=kwargs)


# ---------------------------------------------------------------------------
# State  (immutable — use apply_patches() via the runner, or order.with_update())
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HotelBookingState:
    """Immutable state snapshot passed between hotel booking vertices.

    Persisted across conversation turns by HotelBookingApp which accumulates
    messages and carries forward order + flow between graph runs.

    Attributes:
        messages:       Conversation history (user + assistant turns). Uses
                        operator.add so patches append rather than overwrite.
        order:          Current booking/cancellation transaction in progress.
        final_response: Last TTS-ready response delivered to the guest.
        flow:           Current conversation phase; controls routing in
                        OrderDirectionVertex without an extra LLM call.
    """

    messages: Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    order: Order = field(default_factory=Order)
    final_response: str = ""
    flow: Literal[
        "initial",
        "booking",
        "cancellation",
        "awaiting_confirmation",
    ] = "initial"


# ---------------------------------------------------------------------------
# Patch  (mutable — set only the fields you want to change)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class HotelBookingPatch:
    """Partial update returned by a vertex.

    Fields default to UNSET which means "do not change this field".
    The runner's apply_patches() reads reducers from HotelBookingState type hints,
    so the messages field is automatically appended rather than replaced.
    """

    messages: tuple | object = dataclasses.field(default_factory=lambda: UNSET)
    order: Order | object = dataclasses.field(default_factory=lambda: UNSET)
    final_response: str | object = dataclasses.field(default_factory=lambda: UNSET)
    flow: str | object = dataclasses.field(default_factory=lambda: UNSET)


def initial_state(question: str) -> HotelBookingState:
    """Build the initial state for the very first conversation turn.

    Subsequent turns are handled by HotelBookingApp._build_turn_state() which
    accumulates messages and carries forward order + flow.

    Args:
        question: First user message.

    Returns:
        HotelBookingState with a single user message and empty order.
    """
    msgs: list[dict] = []
    if question:
        msgs.append({"role": "user", "content": question})
    return HotelBookingState(messages=tuple(msgs))
