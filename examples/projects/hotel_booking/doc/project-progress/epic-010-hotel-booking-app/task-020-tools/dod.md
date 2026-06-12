---
apm_category: dod
apm_ref: E010.T020
apm_level: task
created_by: Planner
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Definition of Done — T020 Tool Layer

- [x] `examples/hotel_booking/tools.py` exists with all 7 `ToolBase` subclasses
- [x] All 7 tools implement `execute()` — never raise exceptions
- [x] ISO date parsing errors are caught and returned as strings
- [x] `CreateReservationTool` docstring warns: call only after guest confirmation
- [x] All 12 unit tests in `tests/examples/hotel_booking/test_tools.py` pass
- [x] `uv run pytest tests/examples/hotel_booking/test_tools.py` exits 0
- [x] No linter errors (`uv run ruff check examples/hotel_booking/tools.py`)
- [x] `report.md` written in this directory
