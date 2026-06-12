---
apm_category: dod
apm_ref: E010.T030
apm_level: task
created_by: Planner
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Definition of Done — T030 State Machine

- [x] `examples/hotel_booking/state.py` exists with `HotelState`, `HotelPatch`, `HotelSignal`
- [x] All 19 `HotelSignal` values defined
- [x] `examples/hotel_booking/vertices.py` exists with all 13 vertex classes
- [x] Module-level constants `PERSONA_HEADER`, `TTS_CONSTRAINTS`, `ASR_CONSTRAINTS` are defined
- [x] `IntentParserVertex` includes 4 few-shot examples (one per intent)
- [x] `AskDatesVertex` includes 3 date-format parsing examples in its system prompt
- [x] `DataDispatcherVertex` and `BookingExecutorVertex` have no LLM calls
- [x] `BookingExecutorVertex` guards against `not state.confirmation_pending`
- [x] `OtherHandlerVertex` increments `other_reminder_count` and routes to `done` after 2 reminders
- [x] 4 `DataDispatcherVertex` routing tests pass
- [x] 2 `OtherHandlerVertex` routing tests pass
- [x] `uv run pytest tests/examples/hotel_booking/test_signal_routing.py` exits 0
- [x] No linter errors (`uv run ruff check examples/hotel_booking/state.py examples/hotel_booking/vertices.py`)
- [x] `report.md` written in this directory
