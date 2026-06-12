---
apm_category: task-spec
apm_ref: E010.T050
apm_level: task
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-06-12
updated_at: 2026-06-12
---

# Task T050 — GUI Hotel Book Vue Component

## Goal

Create a custom Vue 3 component `HotelBookPanel.vue` that renders the `HotelBookState`
live-state model as a **hotel guest book** (room × date calendar matrix).
Register it so the existing GUI Live State infrastructure displays it automatically
when the hotel booking app is running in `gui` mode.

This task can be started after T010 is complete (the component only depends on the
`HotelBookState` shape, not on vertices or tools).

---

## Inputs

- `examples/hotel_booking/live_state.py` (T010) — `HotelBookState`, `RoomState`, `Reservation`
- `gui/src/stores/stateViewer.ts` — current live-state store interface
- `gui/src/components/stateviewer/StateViewerPanel.vue` — current rendering entry point
- `gui/src/services/api.ts` — `getLiveState()` response shape
- `examples/agents/06_smart_home_live.py` — reference for `live_state=` in `AgentApp`
- `gui/src/` — Vue/PrimeVue/Pinia project (read-only except the files to create/modify below)

---

## Outputs

### Files to create

- `gui/src/components/stateviewer/HotelBookPanel.vue`

### Files to modify

- `gui/src/components/stateviewer/StateViewerPanel.vue`
  — add a branch to render `HotelBookPanel` when `stateType == "HotelBookState"`

---

## `HotelBookPanel.vue` Specification

### Props

```typescript
interface Props {
  rooms: RoomState[]      // full rooms array from HotelBookState
  lastAction: string      // last_action string, shown in a small status bar
}

interface Reservation {
  reservation_id: string
  guest_name: string
  check_in: string        // ISO date "YYYY-MM-DD"
  check_out: string
  total_price: number
}

interface RoomState {
  room_id: string
  name: string
  capacity: number
  price_per_night: number
  reservations: Reservation[]
}
```

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  🏨 Hotel Guest Book                          [last_action] │
├──────────────┬──────┬──────┬──────┬──────┬──────┬──────────┤
│              │ Jul8 │ Jul9 │Jul10 │Jul11 │Jul12 │   ...    │
├──────────────┼──────┼──────┼──────┼──────┼──────┼──────────┤
│ 🛏 Red ×3    │      │      │Novak │Novak │Novak │          │
│    €120/n    │      │      │      │      │      │          │
├──────────────┼──────┼──────┼──────┼──────┼──────┼──────────┤
│ 🛏 Blue ×2   │Dvora │Dvora │Dvora │      │      │          │
│    €85/n     │      │      │      │      │      │          │
├──────────────┼──────┼──────┼──────┼──────┼──────┼──────────┤
│ 🛏 Green ×2  │      │      │      │      │Horak │          │
│    €85/n     │      │      │      │      │      │          │
├──────────────┼──────┼──────┼──────┼──────┼──────┼──────────┤
│ 🛏 White ×1  │Vesel │      │      │      │      │          │
│    €55/n     │      │      │      │      │      │          │
└──────────────┴──────┴──────┴──────┴──────┴──────┴──────────┘
```

### Column (day) range computation

```typescript
// Build the date column range from all reservations across all rooms
function computeDateRange(rooms: RoomState[]): Date[] {
  // Find min check_in and max check_out across all reservations
  // Show from (min_check_in - 1 day) to (max_check_out) inclusive
  // If no reservations: show today + 7 days
  // Return array of Date objects for each day in range
}
```

### Cell rendering

For each `(room, day)` cell:
- Find if there is a reservation where `check_in <= day < check_out`
- If yes: show `guest_name.substring(0, 5)` with a colored background (amber/orange tint)
- If no: empty cell (light grey background)
- Cell width: fixed `52px`; cell height: `32px`

### Highlight (flash animation)

When `lastAction` changes:
- Apply a CSS class `cell-flash` (amber flash, 0.6s animation) to cells that changed
- Track previous `rooms` snapshot in a `ref` to compute the diff

### Row header

```
🛏 Red Room  ×3 beds  €120/night
```
Fixed width: `160px`. Sticky left (does not scroll with columns).

### Horizontal scroll

The date columns scroll horizontally if there are more than ~10 days. Use CSS `overflow-x: auto`
on the inner table wrapper, with the row header sticky.

### Styling requirements

- Use PrimeVue design tokens for colours where possible (do not hardcode hex values)
- Occupied cell: `var(--p-amber-100)` background with `var(--p-amber-700)` text
- Header row: `var(--p-surface-200)` background
- Responsive: minimum useful width ≈ 480px; graceful on narrow panels

### Status bar (bottom of component)

A single line showing `lastAction` in muted text. Hidden when `lastAction == ""`.

---

## `StateViewerPanel.vue` modifications

Detect the live-state model type by checking `stateData.__class_name__` or the presence
of a `rooms` array with `reservations` sub-arrays:

```typescript
// In StateViewerPanel.vue computed or template:
const isHotelBookState = computed(() =>
  Array.isArray(stateData.value?.rooms) &&
  stateData.value.rooms[0]?.reservations !== undefined
)
```

When `isHotelBookState` is true, render `<HotelBookPanel :rooms="..." :lastAction="..." />`
instead of the generic recursive renderer.

---

## Context Bundle

### Do NOT modify
- `agentflow/` framework source
- `examples/hotel_booking/` Python files
- `gui/src/stores/stateViewer.ts` (read only; do not change store shape)
- `gui/src/services/api.ts`
- `doc/**` other than this task's `dod.md` / `report.md`

### Read
- `examples/hotel_booking/live_state.py` — data shape
- `gui/src/stores/stateViewer.ts` — `stateData` reactive ref shape
- `gui/src/components/stateviewer/StateViewerPanel.vue` — current rendering logic
- `gui/src/components/stateviewer/*.vue` — any existing sub-components for style reference
- `examples/agents/06_smart_home_live.py` — how `live_state=` exposes state to GUI

---

## Dependencies

- T010 must be complete (state shape).
- Can run in parallel with T030 and T040.
- Must be integrated with a running `hotel_booking_app.py` (T040) for full GUI verification.

---

## Test Specification

No automated test file required (Vue component — Vitest unit test is optional).

**Manual verification** (document in `report.md`):

1. Start GUI: `uv run python examples/hotel_booking/hotel_booking_app.py gui`
2. Open browser → hotel book matrix is visible on load (before first question)
3. All 5 seed reservations are visible in the correct cells
4. Ask: "Book the White Room from July 20 to 22 for Brown" → confirm → new cell appears with amber flash
5. Column range expands to include Jul 20–22
6. `lastAction` status bar shows the action description

---

## Definition of Done

See `dod.md` in this directory.
