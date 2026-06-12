---
apm_category: task-spec
apm_ref: E010.T020
apm_level: task
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Task T020 — Tool Layer

## Goal

Implement all 7 agentflow `ToolBase` subclasses that the LLM vertices will use
to read and mutate the shared `_HOTEL` live-state instance.

---

## Inputs

- [`../task-010-data-model/spec.md`](../task-010-data-model/spec.md) — `BookingStore` interface
- `examples/hotel_booking/booking_store.py` — must be complete (T010)
- `examples/hotel_booking/live_state.py` — `_HOTEL` singleton (T010)
- `examples/agents/06_smart_home_live.py` — reference for `ToolBase` + `param_desc` usage
- [`../../../../assignment.en.md`](../../../../assignment.en.md) §4.3, §5, §6.1

---

## Outputs

### Files to create

- `examples/hotel_booking/tools.py`
  — 7 `ToolBase` subclasses (see below)

- `tests/examples/hotel_booking/test_tools.py`
  — unit tests (see Test Specification)

---

## Tool Specifications

All tools operate on a `BookingStore` passed at construction (not the module-level `_HOTEL` directly).
The module-level `_STORE` is built from `_HOTEL` and used in `hotel_booking_app.py`.

```python
from agentflow.tools.Tool import ToolBase, param_desc
```

### `CheckAvailabilityTool`

```
name = "check_availability"
description = "Return available rooms for given check-in date, check-out date, and number of guests."
execute(check_in: str, check_out: str, capacity: str) -> str
  Parses ISO dates. Returns human-readable list of available rooms with prices.
  Returns "No rooms available" if the list is empty.
```

### `GetRoomDetailsTool`

```
name = "get_room_details"
description = "Return name, capacity, and price per night for a specific room."
execute(room_id: str) -> str
  Returns: "Red Room: 3 beds, €120/night." or error string.
```

### `CalculatePriceTool`

```
name = "calculate_price"
description = "Calculate total price for a room and stay duration."
execute(room_id: str, check_in: str, check_out: str) -> str
  Returns: "Red Room from Jul 10 to Jul 14: 4 nights × €120 = €480."
```

### `CreateReservationTool`

```
name = "create_reservation"
description = "Create a room reservation. ONLY call after the guest has explicitly confirmed."
execute(room_id: str, guest_name: str, check_in: str, check_out: str) -> str
  Calls store.create_reservation().
  On success: "Reservation confirmed: Red Room for Novak, Jul 10–14. Total: €480. ID: <uuid>."
  On ValueError: returns error string (never raises).
```

**Important:** The tool's docstring must state:
> "This tool must only be called after the guest has explicitly confirmed the booking summary."

### `CancelReservationTool`

```
name = "cancel_reservation"
description = "Cancel an existing reservation by reservation ID."
execute(reservation_id: str) -> str
  On success: "Reservation <ID> for <guest> cancelled."
  On ValueError: error string.
```

### `FindReservationTool`

```
name = "find_reservation"
description = "Find reservations by guest name, check-in date, or reservation ID. At least one parameter required."
execute(guest_name: str = "", check_in: str = "", reservation_id: str = "") -> str
  Returns formatted list of matching reservations, or "No reservations found."
```

### `FindAlternativesTool`

```
name = "find_alternatives"
description = "Find alternative rooms or dates when a requested room is unavailable."
execute(room_id: str, check_in: str, check_out: str) -> str
  Returns up to 4 alternatives: same room ±3 days, other rooms same dates.
  Formats result as voice-friendly text.
```

---

## Implementation Notes

- **Date parsing:** All tools accept ISO string `"YYYY-MM-DD"`. Use `date.fromisoformat()`.
  On `ValueError` from parsing, return a user-friendly error string (never raise).
- **Error handling:** Tools never raise exceptions from `execute()`.
  All `ValueError` from the store are caught and returned as strings.
- **String format:** Results must be TTS-friendly (no markdown, numbers written naturally where sensible).

---

## Context Bundle

### Do NOT modify
- `agentflow/` framework source
- `examples/hotel_booking/live_state.py` and `booking_store.py` (output of T010)
- `doc/**` other than this task's `dod.md` / `report.md`

### Read
- `examples/hotel_booking/live_state.py` (T010 output)
- `examples/hotel_booking/booking_store.py` (T010 output)
- `agentflow/tools/Tool.py` — `ToolBase`, `param_desc`

---

## Dependencies

- T010 must be complete.

---

## Test Specification

File: `tests/examples/hotel_booking/test_tools.py`

| Test name | Scenario |
|-----------|----------|
| `test_check_availability_returns_results` | Jul 20–22 cap 2 → returns Blue and Green |
| `test_check_availability_no_rooms` | All rooms occupied → "No rooms available" |
| `test_get_room_details_valid` | `room_id="red"` → contains "3 beds" and "120" |
| `test_get_room_details_invalid` | `room_id="purple"` → error string, no exception |
| `test_calculate_price` | Red 3 nights → contains "360" |
| `test_create_reservation_success` | White Jul 20–22 for Smith → success string with ID |
| `test_create_reservation_conflict` | Blue Jul 8–10 → error string, no exception |
| `test_create_reservation_bad_date` | `check_out="not-a-date"` → error string |
| `test_cancel_reservation_success` | Cancel just-created reservation → success string |
| `test_cancel_reservation_not_found` | Random UUID → error string |
| `test_find_reservation_by_name` | `guest_name="Novak"` → returns Novak family entry |
| `test_find_alternatives_returns_options` | Blue Jul 8–11 → at least one alternative |

---

## Definition of Done

See `dod.md` in this directory.
