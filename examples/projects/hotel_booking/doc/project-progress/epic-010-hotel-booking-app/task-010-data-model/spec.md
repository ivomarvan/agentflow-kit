---
apm_category: task-spec
apm_ref: E010.T010
apm_level: task
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Task T010 — Data Model & Booking Store

## Goal

Create the foundational data layer for the hotel booking example:
the `HotelBookState` Pydantic live-state model and the `BookingStore` in-memory
CRUD service with conflict detection, pre-seeded with 5 initial reservations.

---

## Inputs

- [`examples/hotel_booking/assignment.en.md`](../../../../assignment.en.md) — full specification (§2, §3, §5)
- `examples/agents/06_smart_home_live.py` — reference for Pydantic live-state pattern (`HouseState`, `KitchenState`)
- `agentflow/gui/state_viewer.py` — to understand what `icon()` / `room()` annotations do (for reference only; this task does NOT use them — the hotel book needs a custom renderer)

## Outputs

### Files to create

- `examples/hotel_booking/live_state.py`
  - `Reservation(BaseModel)` — reservation record
  - `RoomState(BaseModel)` — single room with its reservation list
  - `HotelBookState(BaseModel, frozen=False)` — top-level live-state object
  - `build_initial_hotel_state() -> HotelBookState` — factory seeding 5 initial reservations (from spec §2.3)
  - Module-level singleton: `_HOTEL = build_initial_hotel_state()`

- `examples/hotel_booking/booking_store.py`
  - `BookingStore` class (operates on a `HotelBookState` instance passed at construction)
  - Methods: `check_availability`, `get_room`, `calculate_price`, `create_reservation`, `cancel_reservation`, `find_reservation`, `find_alternatives`

- `tests/examples/hotel_booking/test_booking_store.py`
  - Unit tests (see Test Specification below)

---

## Detailed Specifications

### `Reservation`

```python
class Reservation(BaseModel):
    model_config = ConfigDict(frozen=False)
    reservation_id: str          # UUID4 string, auto-generated
    guest_name: str
    check_in: date
    check_out: date
    total_price: float           # computed: nights × price_per_night
```

### `RoomState`

```python
class RoomState(BaseModel):
    model_config = ConfigDict(frozen=False)
    room_id: str                 # "red" | "blue" | "green" | "white"
    name: str                    # "Red Room" | ...
    capacity: int                # 3, 2, 2, 1
    price_per_night: float       # 120, 85, 85, 55
    reservations: list[Reservation] = Field(default_factory=list)
```

### `HotelBookState`

```python
class HotelBookState(BaseModel):
    """Top-level live-state model — mutated by tools, observed by GUI Live State panel."""
    model_config = ConfigDict(frozen=False)
    rooms: list[RoomState]       # always all 4 rooms, fixed order: red, blue, green, white
    last_action: str = ""        # human-readable description of the last mutation
```

### `BookingStore` methods

| Method | Signature | Returns | Raises / notes |
|--------|-----------|---------|----------------|
| `check_availability` | `(check_in: date, check_out: date, capacity: int) -> list[RoomState]` | Rooms with no overlapping reservations | — |
| `get_room` | `(room_id: str) -> RoomState` | Room object | `ValueError` if unknown |
| `calculate_price` | `(room_id: str, check_in: date, check_out: date) -> float` | Total price | `ValueError` |
| `create_reservation` | `(room_id: str, guest_name: str, check_in: date, check_out: date) -> Reservation` | Created reservation | `ValueError` if room occupied or dates invalid |
| `cancel_reservation` | `(reservation_id: str) -> Reservation` | Cancelled reservation | `ValueError` if not found |
| `find_reservation` | `(*, guest_name: str = "", check_in: date\|None = None, reservation_id: str = "") -> list[Reservation]` | Matching reservations | Returns empty list |
| `find_alternatives` | `(room_id: str, check_in: date, check_out: date, date_flex_days: int = 3) -> list[dict]` | List of `{room_id, check_in, check_out, reason}` dicts | — |

**Overlap rule:** `new_check_in < existing.check_out AND new_check_out > existing.check_in`

**`create_reservation` must also:**
- Set `reservation.total_price = calculate_price(room_id, check_in, check_out)`
- Append the reservation to `RoomState.reservations`
- Update `_hotel_state.last_action` with a human-readable string

### Seed data (§2.3)

```python
SEED_RESERVATIONS = [
    ("red",   "Novak family",   date(2026, 7, 10), date(2026, 7, 14)),
    ("blue",  "Jana Dvorakova", date(2026, 7,  8), date(2026, 7, 11)),
    ("blue",  "Peter Schmidt",  date(2026, 7, 15), date(2026, 7, 18)),
    ("green", "Marie Horakova", date(2026, 7, 12), date(2026, 7, 15)),
    ("white", "Tomas Vesely",   date(2026, 7,  9), date(2026, 7, 10)),
]
```

---

## Context Bundle

### Do NOT modify
- `agentflow/` (framework source)
- Any other `examples/` file
- `doc/**` files other than this task's own `dod.md` and `report.md`

### Relevant existing files (read only)
- `examples/agents/06_smart_home_live.py` — Pydantic live-state pattern
- `pyproject.toml` — to check Python version and available dependencies
- `src/agentflow/__init__.py` — public API surface

---

## Dependencies

None (this is the first task).

---

## Test Specification

File: `tests/examples/hotel_booking/test_booking_store.py`

Required tests (all `@pytest.mark.unit`):

| Test name | Scenario |
|-----------|----------|
| `test_check_availability_returns_free_rooms` | Query 8–11 Jul, capacity 2 → only Green Room returned |
| `test_check_availability_all_free` | Query 20–25 Jul → all 4 rooms returned |
| `test_create_reservation_success` | Book White Room Jul 20–22 → reservation added, `last_action` updated |
| `test_create_reservation_conflict_raises` | Book Blue Room Jul 8–10 → `ValueError` |
| `test_create_reservation_invalid_dates_raises` | `check_out <= check_in` → `ValueError` |
| `test_cancel_reservation_success` | Cancel by ID → removed from room, returned |
| `test_cancel_reservation_not_found_raises` | Unknown ID → `ValueError` |
| `test_find_reservation_by_name` | `find_reservation(guest_name="Novak")` → 1 result |
| `test_find_alternatives_date_flex` | Conflict on Blue Jul 8–11 → returns Blue ±3 days or Green same dates |
| `test_seed_data_count` | `build_initial_hotel_state()` → 5 total reservations across all rooms |
| `test_calculate_price` | Red Room 3 nights → €360 |

---

## Definition of Done

See `dod.md` in this directory.
