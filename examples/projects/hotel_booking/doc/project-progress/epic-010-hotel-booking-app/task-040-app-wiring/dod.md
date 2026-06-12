---
apm_category: dod
apm_ref: E010.T040
apm_level: task
created_by: Planner
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Definition of Done — T040 App Wiring

- [x] `examples/hotel_booking/hotel_booking_app.py` exists and defines `AgentApp(..., live_state=_HOTEL)`
- [x] State graph contains edges for all 13 vertices and all 19 signals (all reachable from START)
- [x] `uv run python examples/hotel_booking/hotel_booking_app.py --help` exits 0
- [x] `uv run python examples/hotel_booking/hotel_booking_app.py gui` starts without Python errors
- [x] `examples/hotel_booking/README.md` exists with all 7 required sections
- [x] Regression suite: `uv run pytest` exits 0 (no existing tests broken)
- [x] No linter errors (`uv run ruff check examples/hotel_booking/hotel_booking_app.py`)
- [x] `report.md` written in this directory (includes manual smoke test results)
