---
apm_category: task-report
apm_ref: E010.T040
apm_level: task
created_by: Coder
model: claude-4.6-sonnet-medium-thinking
intended_for: Human
created_at: 2026-06-08
updated_at: 2026-06-08
---

# Task Report: E010.T040 — App Wiring

## Co bylo implementováno

`hotel_booking_app.py` propojuje všech 13 vertexů přes `StateGraph` + `Transition`, registruje 7 nástrojů, nastavuje `live_state=_HOTEL` a poskytuje CLI (`run`, `gui`, `graph`). Přidán `README.md` s dokumentací příkladu.

## Vstupy a výstupy

- **Přečteno:** T010–T030 výstupy, `06_smart_home_live.py`, `agentflow/app.py`
- **Vytvořeno:** `hotel_booking_app.py`, `README.md`, `examples/__init__.py`, `examples/hotel_booking/__init__.py`
- **Změněno:** `task-040-app-wiring/dod.md`, `task-040-app-wiring/report.md`

## Použité metody a rozhodnutí

- `agr()` z `git-root-to-syspath` pro spustitelnost skriptu bez ručního `PYTHONPATH`.
- Graf používá deklarativní `Transition` list (stejný vzor jako `06_smart_home.py`).

## Odchylky od spec.md

— Specifikace používá dict-based graph API; implementace používá `StateGraph` + `Transition` (ekvivalentní chování, konzistentní s ostatními příklady).

## Reference do kódu

- `examples/hotel_booking/hotel_booking_app.py:1-150` — AgentApp wiring
- `examples/hotel_booking/README.md` — dokumentace

## Výsledek regresního testu

✅ `uv run pytest` — 413 passed, 2 skipped.

### Manuální smoke testy

| Test | Výsledek |
|------|----------|
| `--help` | ✅ exit 0, zobrazí usage |
| Import modulů | ✅ bez `ModuleNotFoundError` po `agr()` |
| Regresní pytest | ✅ 413/413 |

## Definition of Done

Viz [dod.md](dod.md) — všechna kritéria ✅.
