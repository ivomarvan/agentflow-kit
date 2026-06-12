---
apm_category: epic-plan
apm_ref: E010
apm_level: epic
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Epic E010 — Hotel Booking Voice Assistant

## Goal

Implement a complete hotel booking voice assistant as an `agentflow` example in
`examples/hotel_booking/`. The example demonstrates multi-turn conversation,
hub-and-spoke data collection, safety-gated reservations, an `OTHER` off-topic guard,
and a custom GUI Live State panel showing the hotel guest book.

Full specification: [`../../assignment.en.md`](../../assignment.en.md).

---

## Task List

| Ref     | Task                            | Depends on | Recommended model |
|---------|---------------------------------|------------|-------------------|
| E010.T010 | Data Model & Booking Store    | —          | Composer-2 |
| E010.T020 | Tool Layer                    | T010       | Composer-2 |
| E010.T030 | State Machine (vertices + prompts) | T010, T020 | Composer-2 |
| E010.T040 | App Wiring, CLI, README        | T010–T030  | Composer-2 |
| E010.T050 | GUI Hotel Book Vue Component   | T010       | Composer-2 |

T050 can start in parallel with T030/T040 once T010 is complete.

---

## Deliverables (end of epic)

```
examples/hotel_booking/
├── hotel_booking_app.py        # AgentApp entry point (T040)
├── booking_store.py            # BookingStore + seed data (T010)
├── live_state.py               # HotelBookState Pydantic model (T010)
├── tools.py                    # All 7 ToolBase subclasses (T020)
├── vertices.py                 # All vertices + system prompts (T030)
├── state.py                    # HotelState, HotelPatch, HotelSignal (T030)
├── gui_renderers/
│   └── HotelBookPanel.vue      # Custom Live State component (T050)
├── README.md                   # (T040)
└── doc/project-progress/       # APM docs (this directory)
```

---

## Architecture Summary

```
IntentParserVertex
  ├── NEW_BOOKING   → DataDispatcherVertex (pure Python hub)
  │                       ├── need_name      → AskGuestNameVertex
  │                       ├── need_dates     → AskDatesVertex
  │                       ├── need_capacity  → AskCapacityVertex
  │                       └── data_complete  → AvailabilityCheckerVertex
  │                                              ├── available   → ConfirmationVertex
  │                                              └── unavailable → AlternativesVertex
  │                                                     (alternatives_ok → ConfirmationVertex)
  │                                              confirmed → BookingExecutorVertex
  │                                                          → VoiceFormatterVertex → StdEnd
  ├── CANCELLATION  → CancellationFlowVertex → VoiceFormatterVertex → StdEnd
  ├── INQUIRY       → InquiryVertex → StdEnd
  └── OTHER         → OtherHandlerVertex → IntentParserVertex (max 2×) → StdEnd
```

---

## Key Design Decisions

1. **`DataDispatcherVertex` is pure Python (no LLM).**
   It inspects `HotelState` fields and routes to the right "ask" vertex.
   This is faster, cheaper, and fully deterministic.

2. **Each "ask" vertex has its own LLM call.**
   This splits the data-collection concern into independently testable units and
   makes the state graph easy to follow for students.

3. **`BookingExecutorVertex` is pure Python.**
   It calls `create_reservation` only when `state.confirmation_pending == True`.
   The tool itself has an additional guard for double-safety.

4. **`OtherHandlerVertex` counts reminders in `HotelState.other_reminder_count`.**
   After 2 reminders it routes to `VoiceFormatterVertex` for a polite goodbye.

5. **Live State uses a custom Vue component, not `StateViewerPanel.vue`.**
   The matrix (room × date) layout cannot be expressed with the existing `icon()/room()` API.
   `HotelBookPanel.vue` is registered as a custom renderer via `AgentApp(live_state=_HOTEL)`.

6. **LLM tiers:**
   - Economy (`gpt-4o-mini`): IntentParser, all "ask" vertices, Availability, Alternatives, Inquiry, OtherHandler
   - Quality (`gemini-3.5-flash`): Confirmation, Cancellation, VoiceFormatter

---

## Prompt Engineering Notes (applied per assignment.en.md §9)

Every LLM vertex system prompt must include:
- `<tts_constraints>` block (max 2 sentences, numbers as words, no markdown)
- `<asr_constraints>` block (tolerance, repair pattern, 3-strike rule)
- Emma's persona header (name, role, AI identity declaration)
- Clear output format instruction (enum | voice text | structured list)

Few-shot examples are required in `IntentParserVertex` and `AskDatesVertex` system prompts.
