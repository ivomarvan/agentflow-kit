"""Pydantic live-state models for the hotel booking guest book."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

# Fixed room catalogue — order matters for GUI row display.
_ROOM_CATALOGUE: tuple[tuple[str, str, int, float], ...] = (
    ("red", "Red Room", 3, 120.0),
    ("blue", "Blue Room", 2, 85.0),
    ("green", "Green Room", 2, 85.0),
    ("white", "White Room", 1, 55.0),
)

SEED_RESERVATIONS: tuple[tuple[str, str, date, date], ...] = (
    ("red", "Novak family", date(2026, 7, 10), date(2026, 7, 14)),
    ("blue", "Jana Dvorakova", date(2026, 7, 8), date(2026, 7, 11)),
    ("blue", "Peter Schmidt", date(2026, 7, 15), date(2026, 7, 18)),
    ("green", "Marie Horakova", date(2026, 7, 12), date(2026, 7, 15)),
    ("white", "Tomas Vesely", date(2026, 7, 9), date(2026, 7, 10)),
)


class Reservation(BaseModel):
    """Single room reservation record."""

    model_config = ConfigDict(frozen=False)

    reservation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    guest_name: str
    check_in: date
    check_out: date
    total_price: float


class RoomState(BaseModel):
    """One hotel room with its reservation list."""

    model_config = ConfigDict(frozen=False)

    room_id: str
    name: str
    capacity: int
    price_per_night: float
    reservations: list[Reservation] = Field(default_factory=list)


class HotelBookState(BaseModel):
    """Top-level live-state model — mutated by tools, observed by GUI Live State panel."""

    model_config = ConfigDict(frozen=False)

    rooms: list[RoomState]
    last_action: str = ""


def _nights(check_in: date, check_out: date) -> int:
    """Return stay length in nights (check_out is departure morning)."""
    return (check_out - check_in).days


def build_initial_hotel_state() -> HotelBookState:
    """Create a fresh hotel state with four rooms and five seed reservations."""
    rooms = [
        RoomState(room_id=room_id, name=name, capacity=capacity, price_per_night=price)
        for room_id, name, capacity, price in _ROOM_CATALOGUE
    ]
    room_by_id = {room.room_id: room for room in rooms}

    for room_id, guest_name, check_in, check_out in SEED_RESERVATIONS:
        room = room_by_id[room_id]
        nights = _nights(check_in, check_out)
        room.reservations.append(
            Reservation(
                guest_name=guest_name,
                check_in=check_in,
                check_out=check_out,
                total_price=nights * room.price_per_night,
            )
        )

    return HotelBookState(rooms=rooms, last_action="")


_HOTEL = build_initial_hotel_state()
