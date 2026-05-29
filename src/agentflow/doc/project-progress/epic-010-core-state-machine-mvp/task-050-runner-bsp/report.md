---
apm_category: task-report
apm_ref: E010.T050
apm_level: task
created_by: Coder
model: claude-sonnet-4-6
intended_for: Human
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Report: E010.T050 — StateGraphRunner with BSP loop

## Co bylo implementováno

Implementován `StateGraphRunner` — jádro execution enginu pro BSP (Bulk Synchronous Parallel) smyčku.
Třída přijímá `StateGraph`, `Context` a volitelné `RunnerHooks` (defaultně `NoOpHooks()`).
Async metoda `run(initial_state)` provádí smyčku: End uzly spouští první → pak `asyncio.gather` (Compute) → `apply_patches` (Apply) → set-based route (Route).
`_safe_run` zachytí jakoukoli výjimku, zaloguje ji přes `log.exception`, zavolá `hooks.on_vertex_error` a vrátí `(StdSignal.fail, _EmptyPatch())`.
Synchronní wrapper `run_sync` volá `asyncio.run(self.run(...))`.
`StateGraphRunner` přidán do `__all__` v `statemachine/__init__.py`.

## Vstupy a výstupy

- **Přečteno:** `src/agentflow/statemachine/runner.py` (placeholder), `topology.py`, `vertex.py`, `context.py`, `hooks.py`, `state.py`, `testing/fakes.py`, `testing/__init__.py`, `testing/fixtures.py`, `statemachine/__init__.py`, spec.md, dod.md
- **Změněno:** `src/agentflow/statemachine/runner.py` (placeholder → kompletní implementace), `src/agentflow/statemachine/__init__.py` (přidán re-export `StateGraphRunner`)
- **Vytvořeno:** `src/agentflow/tests/statemachine/test_runner_bsp.py`

## Použité metody a rozhodnutí

- **BSP pořadí fází:** End uzly se zpracovávají na začátku každé iterace while smyčky — pokud po jejich spuštění nezůstanou žádné non-End uzly, loop okamžitě skončí. Tím je zaručeno, že End.run() je vždy zavoláno.
- **Set-based join:** `next_set: set[StateVertex]` automaticky dedupuje vrcholy pomocí object identity — dvě větve vedoucí na stejnou instanci vertex ji naplánují jen jednou.
- **`_safe_run` import `_EmptyPatch` lokálně:** Import `_EmptyPatch` je uvnitř except bloku (local import), aby se předešlo případným circular import problémům. Tato technika je konzistentní s existujícím vzorem v `vertex.py`.
- **`NoOpHooks` typování:** mypy strict nevyžadoval `# type: ignore[assignment]` — `NoOpHooks` je rozpoznán jako kompatibilní s Protocol `RunnerHooks` strukturálně.
- **Test stav `_AppState`:** Jméno začíná `_` aby pytest třídu nesnažil sbírat jako test suite (jinak by produkoval `PytestCollectionWarning`).

## Odchylky od spec.md

- Spec uvádí `hooks or NoOpHooks()` syntaxi; implementace používá explicitní `hooks if hooks is not None else NoOpHooks()` — sémanticky ekvivalentní, ale bezpečnější (falsy custom hooks objekt by byl nesprávně nahrazen).
- `# type: ignore[assignment]` zmíněný v spec.md sec. 9 nebyl potřeba — mypy strict tuto přiřazení akceptoval bez komentáře.

## Reference do kódu

- `src/agentflow/statemachine/runner.py:1-127` — kompletní `StateGraphRunner` implementace
- `src/agentflow/statemachine/__init__.py:9-35` — re-export `StateGraphRunner`
- `src/agentflow/tests/statemachine/test_runner_bsp.py:1-200` — 6 unit testů BSP smyčky

## Výsledek regresního testu

✅ Všechny testy projdou (41/41).
✅ `mypy --strict --follow-imports=skip src/agentflow/statemachine/` — 0 issues.
✅ `ruff check` — čistý.
⚠️ `ruff format --check` — `topology.py` (T040, mimo scope) vyžaduje drobné přeformátování; soubory T050 jsou formátově čisté.

## Definition of Done

Viz [dod.md](dod.md) — všechna kritéria ✅ (jedna ❌ pro pre-existující ruff format issue v `topology.py` mimo scope T050).
