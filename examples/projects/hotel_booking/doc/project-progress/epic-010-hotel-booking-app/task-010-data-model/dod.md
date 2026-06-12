---
apm_category: dod
apm_ref: E010.T010
apm_level: task
created_by: Planner
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Definition of Done — T010 Data Model & Booking Store

- [x] `examples/hotel_booking/live_state.py` exists with `Reservation`, `RoomState`, `HotelBookState`, `build_initial_hotel_state()`, `_HOTEL`
- [x] `examples/hotel_booking/booking_store.py` exists with `BookingStore` and all 7 methods
- [x] `build_initial_hotel_state()` seeds exactly 5 reservations matching spec §2.3
- [x] Overlap detection follows rule: `new_check_in < existing.check_out AND new_check_out > existing.check_in`
- [x] `create_reservation` raises `ValueError` on conflict or invalid dates
- [x] `cancel_reservation` raises `ValueError` on unknown ID
- [x] `last_action` is updated on every `create_reservation` and `cancel_reservation` call
- [x] All 11 unit tests in `tests/examples/hotel_booking/test_booking_store.py` pass
- [x] `uv run pytest tests/examples/hotel_booking/test_booking_store.py` exits 0
- [x] No linter errors (`uv run ruff check examples/hotel_booking/live_state.py examples/hotel_booking/booking_store.py`)
- [x] `report.md` written in this directory
