"""In-memory reservation store — works without GUI, GUI just visualizes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Reservation:
    """A single hotel room reservation.

    Attributes:
        guest_name: Full name of the guest.
        room: Room number or type.
        check_in: Check-in date string.
        check_out: Check-out date string.
        created_at: ISO timestamp of when the reservation was created.
    """

    guest_name: str
    room: str
    check_in: str
    check_out: str
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


class ReservationStore:
    """Thread-safe in-memory store for reservations.

    Stores Reservation instances in a plain list.  Thread safety is provided
    by the Python GIL for single-process use cases — sufficient for demos.
    """

    def __init__(self) -> None:
        self._reservations: list[Reservation] = []

    def add(self, reservation: Reservation) -> None:
        """Append a new reservation to the store.

        Args:
            reservation: Fully populated Reservation instance.
        """
        self._reservations.append(reservation)

    @property
    def all(self) -> list[Reservation]:
        """Return a snapshot of all stored reservations.

        Returns:
            New list containing all Reservation instances in insertion order.
        """
        return list(self._reservations)

    def __len__(self) -> int:
        return len(self._reservations)
