"""Tool: find_alternatives — suggest alternate rooms or dates when requested stay is unavailable."""

from __future__ import annotations

from datetime import date

from agentflow.tools.Tool import ToolBase, param_desc
from ..booking_store import BookingStore
from ._helpers import format_date, parse_date


class FindAlternativesTool(ToolBase):
    """Suggest alternate rooms or dates when the requested stay is unavailable."""

    name = "find_alternatives"
    description = "Find alternative rooms or dates when a requested room is unavailable."

    def __init__(self, store: BookingStore) -> None:
        self._store = store

    @param_desc(
        room_id="Requested room ID.",
        check_in="Check-in date in YYYY-MM-DD format.",
        check_out="Check-out date in YYYY-MM-DD format.",
    )
    def execute(self, room_id: str, check_in: str, check_out: str) -> str:
        """Format up to four voice-friendly alternatives."""
        check_in_d = parse_date(check_in)
        if isinstance(check_in_d, str):
            return check_in_d
        check_out_d = parse_date(check_out)
        if isinstance(check_out_d, str):
            return check_out_d
        try:
            alternatives = self._store.find_alternatives(room_id, check_in_d, check_out_d)
        except ValueError as exc:
            return str(exc)
        if not alternatives:
            return "No alternatives found for those dates."
        lines: list[str] = []
        for alt in alternatives[:4]:
            alt_room = self._store.get_room(str(alt["room_id"]))
            alt_in = alt["check_in"]
            alt_out = alt["check_out"]
            assert isinstance(alt_in, date)
            assert isinstance(alt_out, date)
            lines.append(
                f"{alt_room.name} {format_date(alt_in)} to {format_date(alt_out)} "
                f"({alt['reason']})"
            )
        return "Alternatives: " + "; ".join(lines)
