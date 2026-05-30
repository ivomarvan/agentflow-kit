---
apm_category: task-report
apm_ref: E010.T040
apm_level: task
created_by: Coder
model: claude-sonnet-4-6
intended_for: Human
created_at: 2026-05-28
updated_at: 2026-05-28
---

# Task Report: E010.T040 — Topology: Transition, Parallel, StateGraph

## Co bylo implementováno

Soubor `topology.py` byl kompletně implementován: nahrazen placeholder třemi produkčními třídami.
`Transition` je immutable `@dataclass(frozen=True)` reprezentující hranu grafu.
`Parallel` je fan-out marker s metodou `expand()` vracející flat list vertex instancí.
`StateGraph` drží topologii (start + list přechodů) a poskytuje query metody (`resolve_start`, `get_targets`, `expand_target`, `apply_patches`) používané runnerem v BSP fázi Apply&Route.
Validace v `_validate_no_classes` brání záměně třídy za instanci a ukazuje na E020.

## Vstupy a výstupy

- **Přečteno:** `spec.md`, `dod.md`, `state.py` (T020), `vertex.py` (T030), `signal.py` (T010), `__init__.py`
- **Nahrazeno/Vytvořeno:** `src/agentflow/statemachine/topology.py` (placeholder → plná implementace)
- **Vytvořeno:** `src/agentflow/tests/statemachine/test_topology.py` (7 unit testů)
- **Změněno:** `src/agentflow/statemachine/__init__.py` (přidány re-exporty `Transition`, `Parallel`, `StateGraph`)

## Použité metody a rozhodnutí

- `get_targets` porovnává `from_node` i `signal` pomocí identity (`is`) — Enum members jsou singletons, takže `is` je korektní a výkonově levnější než `==`.
- `StateGraph.apply_patches` deleguje přímo na standalone `apply_patches()` z `state.py` bez další logiky — čistá delegace bez duplikace.
- `_validate_no_classes` iteruje přes všechna pole `Transition` a kontroluje `isinstance(node, type)` — třída je vždy instancí `type`, takže tato podmínka spolehlivě rozlišuje třídu od instance.
- Pro testy byly deklarovány minimální `_AVertex`, `_BVertex`, `_CVertex` přímo v test souboru (FakeVertex z T070 ještě neexistuje).
- Nevyužitý `type: ignore[arg-type]` komentář (z návrhu ve spec.md) byl odstraněn — mypy `--strict` hlásí `unused-ignore` jako error.

## Odchylky od spec.md

- **Odstraněn** `# type: ignore[arg-type]` komentář u `apply_patches` delegace (spec.md ho navrhoval). Mypy `--strict` hlásí `unused-ignore` jako error, protože signatury jsou kompatibilní a ignore je zbytečný. Dopad: žádný — kód funguje identicky.

## Reference do kódu

- `src/agentflow/statemachine/topology.py:1–149` — kompletní implementace Transition, Parallel, StateGraph
- `src/agentflow/statemachine/__init__.py:1–34` — re-exporty včetně nových symbolů
- `src/agentflow/tests/statemachine/test_topology.py:1–109` — 7 unit testů

## Výsledek regresního testu

✅ Všechny testy projdou (30/30). Žádné regrese.

```
pytest src/agentflow/tests/statemachine/ -v
30 passed in 0.14s
```

```
mypy --strict --follow-imports=skip src/agentflow/statemachine/
Success: no issues found in 8 source files
```

```
ruff check src/agentflow/statemachine/ src/agentflow/tests/statemachine/
All checks passed!
```

## Definition of Done

Viz [dod.md](dod.md) — všechna kritéria ✅.
