---
apm_category: epic-plan
apm_ref: E101
apm_level: epic
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-05-30
updated_at: 2026-05-30
approved_by: Human
approved_at: 2026-05-30
---

# Epic E101 — DisplayTool + HotelBookingApp příklad

**Cíl:** Demonstrovat plný GUI workflow na `HotelBookingApp` — aplikaci s vlastním
domain eventem `ReservationEvent` a custom Vue rendererem. Zavést konvenci `gui_renderers/`
adresáře vedle aplikace a build skript pro auto-generování event renderer registry.

---

## Scope

| Oblast | Co se mění |
|--------|-----------|
| `examples/hotel_booking/` (nový) | `HotelBookingApp` + `HotelBookingTool` |
| `examples/hotel_booking/gui_renderers/` (nový) | `hotel_reservation.vue` custom renderer |
| `agentflow/gui/build.py` | Auto-discovery `gui_renderers/` + generování `index.ts` |
| `gui/src/event-renderers/index.ts` | Generovaný soubor (do .gitignore) |
| `examples/hotel_booking/README.md` (nový) | Dokumentace příkladu |

---

## Task List

| Task | Název | Závisí na |
|------|-------|-----------|
| T010 | `HotelBookingTool` + `ReservationEvent` + `HotelBookingApp` | E096 |
| T020 | `hotel_reservation.vue` custom renderer | E098 |
| T030 | Build skript: auto-discovery `gui_renderers/` + generování `index.ts` | T020 |
| T040 | README + demo flow dokumentace | T030 |

---

## T010 — HotelBookingApp

### Architektura

```
examples/hotel_booking/
    __init__.py
    hotel_booking_app.py         ← AgentApp subclass
    hotel_booking_tool.py        ← Tool s EventBus emisí
    reservation_store.py         ← in-memory store (list v paměti)
    gui_renderers/
        hotel_reservation.vue
    README.md
```

### `reservation_store.py`

```python
@dataclass
class Reservation:
    guest_name: str
    room: str
    check_in: str
    check_out: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

class ReservationStore:
    """In-memory reservation store — works without GUI, GUI just visualizes."""
    def __init__(self) -> None:
        self._reservations: list[Reservation] = []

    def add(self, r: Reservation) -> None:
        self._reservations.append(r)

    @property
    def all(self) -> list[Reservation]:
        return list(self._reservations)
```

### `hotel_booking_tool.py`

```python
from agentflow.events import AgentEvent
from pydantic import BaseModel
from typing import Literal

class ReservationEvent(AgentEvent):
    """Domain event emitted when a reservation is created."""
    event_type: Literal["hotel.reservation"] = "hotel.reservation"
    guest_name: str
    room: str
    check_in: str
    check_out: str

class HotelBookingTool(ToolBase):
    """Books hotel rooms. Stores to ReservationStore; emits ReservationEvent to EventBus."""

    def __init__(self, store: ReservationStore, event_bus_ref: Callable) -> None:
        self._store = store
        self._get_event_bus = event_bus_ref  # lazy ref — ctx.event_bus při run()

    async def run(self, guest_name: str, room: str, check_in: str, check_out: str) -> str:
        r = Reservation(guest_name, room, check_in, check_out)
        self._store.add(r)
        await self._get_event_bus().emit(ReservationEvent(
            guest_name=guest_name, room=room, check_in=check_in, check_out=check_out
        ))
        return f"Room {room} booked for {guest_name} ({check_in} – {check_out})."
```

### `hotel_booking_app.py`

```python
class HotelBookingApp(AgentApp):
    """Hotel booking agent — demonstrates domain events + custom GUI renderer."""

    @property
    def sample_prompts(self) -> list[str]:
        return [
            "Book a single room for John Smith from Dec 1 to Dec 5",
            "Reserve a double room for Mary Jones next Friday for 3 nights",
            "Book room 101 for Bob Brown from 2024-12-20 to 2024-12-23",
        ]

    async def run_workflow(self) -> str | None:
        ...
        return f"Booked {len(self._store.all)} reservations total."
```

Používá `FakeLlmConnector` takže nevyžaduje API klíč — vhodné pro demo a vývoj GUI.

---

## T020 — Custom Vue renderer

### `examples/hotel_booking/gui_renderers/hotel_reservation.vue`

```vue
<template>
  <div class="reservation-event">
    <DataTable :value="[event]" size="small">
      <Column field="guest_name" header="Guest" />
      <Column field="room"       header="Room" />
      <Column field="check_in"   header="Check-in" />
      <Column field="check_out"  header="Check-out" />
    </DataTable>
  </div>
</template>

<script setup lang="ts">
import { DataTable, Column } from 'primevue'
defineProps<{ event: Record<string, unknown> }>()
</script>
```

---

## T030 — Build skript: auto-discovery

### Konvence `gui_renderers/`

Framework hledá `gui_renderers/*.vue` v:
1. Adresáři vedle Python skriptu (konvence)
2. Cestách deklarovaných v `AgentApp.gui_renderer_paths: list[Path]` (explicitní override)

### `agentflow/gui/build.py` — rozšíření

```python
def discover_renderers(app: AgentApp) -> list[tuple[str, Path]]:
    """Find .vue renderer files via convention or explicit declaration.

    Returns list of (event_type, vue_file_path) tuples.
    Convention: event_type = filename with _ replaced by . and .vue stripped
    (e.g. hotel_reservation.vue → hotel.reservation)
    """
    ...

def generate_renderer_index(renderers: list[tuple[str, Path]], output: Path) -> None:
    """Auto-generate gui/src/event-renderers/index.ts from discovered renderers."""
    ...
```

### `.gitignore` v `gui/src/event-renderers/`

```gitignore
# Auto-generated by agentflow-gui build script — do not edit manually
index.ts
```

Statické soubory (GenericJsonRenderer.vue) jsou commitnuty. `index.ts` je generovaný.

### Build flow při `python script.py gui`

```
1. discover_renderers(self)          → list[(event_type, path)]
2. generate_renderer_index(...)      → gui/src/event-renderers/index.ts
3. check_build()                     → aktuální?
4. ensure_build(interactive=True)    → přestavět pokud zastaralý
5. serve(self, ...)                  → FastAPI + browser
```

---

## T040 — README + demo dokumentace

### `examples/hotel_booking/README.md`

- Co příklad demonstruje
- Jak spustit: `uv run python examples/hotel_booking/hotel_booking_app.py gui`
- Jak přidat vlastní renderer (custom event)
- Architektura: `ReservationStore` + `HotelBookingTool` + `ReservationEvent` + GUI renderer

### Aktualizace root `README.md`

- Přidat sekci "GUI Demo" s krátkým popisem a screenshotem (nebo animovaný GIF)

---

## Epic E101 Definition of Done

- [ ] `HotelBookingApp` spustitelný s `FakeLlmConnector` bez API klíče
- [ ] `ReservationEvent` emitován do `EventBus` při každé rezervaci
- [ ] GUI zobrazí `hotel_reservation.vue` tabulku místo generického JSON
- [ ] Build skript auto-generuje `index.ts` z `gui_renderers/hotel_reservation.vue`
- [ ] `sample_prompts` zobrazeny v GUI jako klikatelné chips
- [ ] `examples/hotel_booking/README.md` kompletní
- [ ] Root `README.md` zmíní GUI demo
