"""Agent state, patch, and routing signals for the hotel booking workflow."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated

from agentflow.statemachine import Signal


@dataclass(frozen=True)
class HotelState:
    """Immutable state snapshot passed between hotel booking vertices."""

    messages: Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    intent: str = ""
    guest_name: str = ""
    check_in: str = ""
    check_out: str = ""
    capacity: int = 0
    selected_room_id: str = ""
    total_price: float = 0.0
    reservation_id: str = ""
    alternatives: tuple[dict, ...] = field(default_factory=tuple)
    confirmation_pending: bool = False
    other_reminder_count: int = 0
    final_response: str = ""


@dataclass(frozen=True)
class HotelPatch:
    """Partial update returned by a vertex; only set fields that changed."""

    intent: str | None = None
    guest_name: str | None = None
    check_in: str | None = None
    check_out: str | None = None
    capacity: int | None = None
    selected_room_id: str | None = None
    total_price: float | None = None
    reservation_id: str | None = None
    alternatives: tuple[dict, ...] | None = None
    confirmation_pending: bool | None = None
    other_reminder_count: int | None = None
    final_response: str | None = None


class HotelSignal(Signal):
    """Routing decisions for the hotel booking state graph."""

    intent_new = "intent_new"
    intent_cancel = "intent_cancel"
    intent_inquiry = "intent_inquiry"
    intent_other = "intent_other"
    reminder_sent = "reminder_sent"
    data_complete = "data_complete"
    need_name = "need_name"
    need_dates = "need_dates"
    need_capacity = "need_capacity"
    name_collected = "name_collected"
    dates_collected = "dates_collected"
    capacity_collected = "capacity_collected"
    available = "available"
    unavailable = "unavailable"
    confirmed = "confirmed"
    declined = "declined"
    alternatives_ok = "alternatives_ok"
    cancelled = "cancelled"
    done = "done"
