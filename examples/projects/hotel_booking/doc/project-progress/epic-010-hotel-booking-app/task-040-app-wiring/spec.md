---
apm_category: task-spec
apm_ref: E010.T040
apm_level: task
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Task T040 — App Wiring, CLI, and README

## Goal

Wire all components (state, tools, vertices) into a runnable `AgentApp`,
configure the state graph (edges), add the live-state hook to expose `_HOTEL`
to the GUI, verify that both `run` and `gui` modes work end-to-end,
and write `README.md` for the example.

---

## Inputs

- `examples/hotel_booking/live_state.py` (T010) — `_HOTEL`
- `examples/hotel_booking/booking_store.py` (T010) — `BookingStore`, `_STORE`
- `examples/hotel_booking/tools.py` (T020) — all 7 tools
- `examples/hotel_booking/state.py` (T030) — `HotelState`, `HotelPatch`, `HotelSignal`
- `examples/hotel_booking/vertices.py` (T030) — all 13 vertices
- `examples/agents/06_smart_home_live.py` — reference for `AgentApp` configuration with `live_state`
- `src/agentflow/app.py` — `AgentApp` constructor signature
- [`../../../../assignment.en.md`](../../../../assignment.en.md)

---

## Outputs

### Files to create / modify

- `examples/hotel_booking/hotel_booking_app.py` — main application script
- `examples/hotel_booking/README.md` — example documentation

---

## `hotel_booking_app.py` Specification

### Module-level objects

```python
# Shared mutable state — observed by GUI Live State panel
from examples.hotel_booking.live_state import _HOTEL

# Booking store — wraps _HOTEL, used by tools
from examples.hotel_booking.booking_store import BookingStore
_STORE = BookingStore(_HOTEL)

# Instantiate tools — each gets _STORE at construction
_TOOLS = [
    CheckAvailabilityTool(_STORE),
    GetRoomDetailsTool(_STORE),
    CalculatePriceTool(_STORE),
    CreateReservationTool(_STORE),
    CancelReservationTool(_STORE),
    FindReservationTool(_STORE),
    FindAlternativesTool(_STORE),
]
```

### State graph (edges)

```python
graph = {
    START:                      IntentParserVertex,
    IntentParserVertex: {
        HotelSignal.intent_new:       DataDispatcherVertex,
        HotelSignal.intent_cancel:    CancellationFlowVertex,
        HotelSignal.intent_inquiry:   InquiryVertex,
        HotelSignal.intent_other:     OtherHandlerVertex,
    },
    DataDispatcherVertex: {
        HotelSignal.need_name:        AskGuestNameVertex,
        HotelSignal.need_dates:       AskDatesVertex,
        HotelSignal.need_capacity:    AskCapacityVertex,
        HotelSignal.data_complete:    AvailabilityCheckerVertex,
    },
    AskGuestNameVertex:    { HotelSignal.name_collected:      DataDispatcherVertex },
    AskDatesVertex:        { HotelSignal.dates_collected:     DataDispatcherVertex },
    AskCapacityVertex:     { HotelSignal.capacity_collected:  DataDispatcherVertex },
    AvailabilityCheckerVertex: {
        HotelSignal.available:    ConfirmationVertex,
        HotelSignal.unavailable:  AlternativesVertex,
    },
    AlternativesVertex: {
        HotelSignal.alternatives_ok:  ConfirmationVertex,
        HotelSignal.declined:         END,
    },
    ConfirmationVertex: {
        HotelSignal.confirmed:   BookingExecutorVertex,
        HotelSignal.declined:    END,
    },
    BookingExecutorVertex: { HotelSignal.done: VoiceFormatterVertex },
    CancellationFlowVertex: {
        HotelSignal.done:      VoiceFormatterVertex,
        HotelSignal.declined:  END,
    },
    InquiryVertex:       { HotelSignal.done: END },
    OtherHandlerVertex: {
        HotelSignal.reminder_sent:  IntentParserVertex,
        HotelSignal.done:           END,
    },
    VoiceFormatterVertex: { HotelSignal.done: END },
}
```

### `AgentApp` configuration

```python
app = AgentApp(
    name="Hotel Booking Voice Assistant",
    description="Emma — virtual receptionist at the Four Colours Hotel.",
    state_type=HotelState,
    patch_type=HotelPatch,
    graph=graph,
    tools=_TOOLS,
    live_state=_HOTEL,
    default_question="I'd like to make a room reservation.",
)
```

### CLI entry point

```python
if __name__ == "__main__":
    app.run()
```

`app.run()` must support `--help`, `run` (interactive CLI), and `gui` subcommands.

---

## README.md Specification

Required sections:

1. **Overview** — what this example demonstrates (2–3 sentences)
2. **Run modes**
   - `uv run python examples/hotel_booking/hotel_booking_app.py run`
   - `uv run python examples/hotel_booking/hotel_booking_app.py gui`
3. **Agent architecture** — brief description of each vertex and its role
4. **Prompt engineering highlights** — which principles from the course are illustrated
5. **Sample questions** — 5 sample inputs (new booking, cancellation, inquiry, conflict, off-topic)
6. **Live State panel** — note that the GUI shows a hotel guest book in `HotelBookPanel.vue`
7. **Extending the example** — suggestions: add room photos, loyalty discounts, email confirmation

---

## Context Bundle

### Do NOT modify
- `agentflow/` framework source
- `examples/hotel_booking/live_state.py`, `booking_store.py`, `tools.py`, `state.py`, `vertices.py`
- `doc/**` other than this task's `dod.md` / `report.md`

### Read
- All T010–T030 output files
- `examples/agents/06_smart_home_live.py` — AgentApp wiring reference
- `src/agentflow/app.py` — AgentApp constructor

---

## Dependencies

- T010, T020, T030 must be complete.

---

## Test Specification

No new automated test file required.

**Manual smoke test** (must be documented in `report.md`):

1. `uv run python examples/hotel_booking/hotel_booking_app.py --help` — exits 0, shows help text
2. `uv run python examples/hotel_booking/hotel_booking_app.py run` with input
   "Book a room for two from July 20 to 22 for Smith" → reaches `BookingExecutorVertex`
3. Full regression suite still passes: `uv run pytest` → exits 0

---

## Definition of Done

See `dod.md` in this directory.
