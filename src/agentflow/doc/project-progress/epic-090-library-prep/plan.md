# Epic E090 — Příprava knihovny pro veřejné publikování

**Cíl:** Transformovat soukromý výukový projekt na veřejně publikovatelnou open-source
knihovnu. Odstraníme `git_root_to_syspath`, přejdeme na editable install, vyčistíme
osobní/firemní reference z dokumentace a přidáme srovnávací tabulku s konkurencí.

**Root:** `src/agentflow/` (framework) + `src/examples/` + `src/projects/`

---

## Scope

| Oblast | Co se mění |
|--------|-----------|
| `pyproject.toml` | Přidání `[tool.setuptools.packages.find]` + `where = ["src"]` |
| ~30 souborů s `agr()` | Odstranění `git_root_to_syspath`, oprava importů |
| `src/projects/` README + `doc/` briefy | Smazání firemních referencí (Mama AI, Telma, Adéla) |
| `src/examples/self_education/Agentni_systemy/` | Přejmenování na `src/examples/patterns/` |
| `README.md` (root) | Rewrite jako veřejné README open-source projektu |
| `src/agentflow/README.md` | Doplnění srovnávací tabulky s LangGraph/CrewAI |
| `src/projects/How_to_use_AI_in_programming-recommendations.md` | Posoudit: přesunout do `doc/guides/` nebo odebrat |

---

## Task List

| Task | Název | Závisí na |
|------|-------|-----------|
| T010 | Editable install + masová náhrada `agr()` | — |
| T020 | Cleanup osobních/firemních referencí v docs | T010 |
| T030 | Veřejné README + srovnávací tabulka s konkurencí | T020 |

---

## T010 — Editable Install + Odstranění `agr()`

**Cíl:** Po dokončení tohoto tasku funguje `from agentflow.xxx import yyy` v celém projektu
bez jakékoli `sys.path` magie.

### Krok 1: Oprava `pyproject.toml`

Přidat setuptools konfiguraci pro `src/` layout:
```toml
[tool.setuptools.packages.find]
where = ["src"]
```

Tím setuptools najde balíček `agentflow` v `src/agentflow/`. Dále odebrat
`git-root-to-syspath` ze `dependencies` (zbývá v `pyproject.toml` jako komentář
nebo se přesune do `dev` pro zpětnou kompatibilitu).

Spustit: `uv pip install -e .`

### Krok 2: Hromadná náhrada importů

Ve VŠECH souborech (framework + examples + tests):

```python
# ODEBRAT tyto dva řádky (jsou různé varianty):
from git_root_to_syspath import agr
agr()

# ZMĚNIT import prefix:
# from src.agentflow.xxx → from agentflow.xxx
# from src.examples.xxx  → zachovat nebo přesunout
```

Postup:
1. `grep -rn "from git_root_to_syspath\|agr()" src/ --include="*.py" -l` → seznam souborů
2. Hromadná náhrada přes `sed` nebo per-file StrReplace
3. Oprava `from src.agentflow.` → `from agentflow.` ve všech souborech

### Krok 3: Verifikace

```bash
uv pip install -e .
uv run pytest src/agentflow/tests/ -v -m "not integration"
python src/examples/statemachine_demos/01_brief_example.py
python src/examples/statemachine_demos/04_parallel_research_loop.py
uv run mypy --strict src/agentflow/statemachine/
uv run ruff check src/
```

**Výstupy:**
- `pyproject.toml` upraven
- ~30 Python souborů bez `agr()`
- Všechny testy zelené
- Demo skripty spustitelné

---

## T020 — Cleanup Osobních a Firemních Referencí

**Cíl:** Žádný veřejný soubor v repozitáři nesmí obsahovat reference na konkrétní firmy
z pracovního pohovoru.

### Soubory s firemními referencemi

Podle grepu jsou to (nutno ověřit a projít ručně):
- `src/projects/README.md` — "Mama AI / Telma", "Adéla", "technické kolo" → přepsat
- `src/projects/01_structured_extraction/doc/project-progress/brief.md` — ověřit
- `src/projects/02_rag_faq_bot/doc/project-progress/brief.md` — ověřit
- `src/projects/03_tool_calling_agent/doc/project-progress/brief.md` — ověřit
- `src/projects/04_llm_evaluator/doc/project-progress/brief.md` — ověřit
- `src/projects/05_voicebot_hr_screening/doc/project-progress/brief.md` — ověřit
- `src/projects/How_to_use_AI_in_programming-recommendations.md` — posoudit

### Pravidlo pro přepis

Zachovat obsah projektu (co se dělá a proč), pouze generalizovat kontext:

```markdown
# PŘED:
Sada cvičných projektů pro technický pohovor pro pozici AI Agent Developer v Mama AI / Telma.

# PO:
Sada referenčních projektů pokrývající typické úkoly AI Agent Developera.
Každý projekt procvičuje jednu konkrétní dovednost.
```

Technické detaily (co projekt dělá, jaké technologie, dovednosti) **zachovat** —
jsou hodnotné pro každého čtenáře.

### Přejmenování examples adresáře

```
src/examples/self_education/Agentni_systemy/ → src/examples/patterns/
```
Přesunout:
- `orig/` → `src/examples/patterns/frameworks/` (LangGraph, CrewAI příklady)
- `my/` → `src/examples/patterns/` (naše implementace)

---

## T030 — Veřejné README + Srovnávací Tabulka

**Cíl:** Profesionální root `README.md` a doplnění srovnávací tabulky.

### Root `README.md` — nová struktura

```markdown
# agentflow — Declarative AI Agent Orchestration

One-paragraph popis: what it is, why BSP, co umí.

## Features
## Quick Install
## Hello World (10 řádků)
## Why agentflow? (comparison table)
## Examples
## Documentation
## Project Status & Roadmap
```

### Srovnávací tabulka (do `src/agentflow/README.md` nebo root README)

| Feature | **agentflow** | LangGraph | CrewAI |
|---------|--------------|-----------|--------|
| Execution model | BSP (deterministic super-steps) | Event-driven DAG | Role-based multi-agent |
| State management | Frozen dataclasses + reducers | TypedDict (mutable) | Pydantic models |
| Parallel execution | `Parallel(A, B)` with barrier | `Send()` API | Agent delegation |
| Graph visualization | Built-in SVG/HTML/DOT (Describable) | LangSmith (external) | — |
| Checkpointing | Protocol-based (memory/file/DB) | PostgreSQL/Redis savers | — |
| Pause/resume | `run_until()` + `resume()` | `interrupt_before` | — |
| Type safety | mypy --strict, frozen state | Partial | Partial |
| LLM agnostic | Yes (connector protocol) | Yes | Yes |
| **Missing** | Streaming tokens, distributed execution | — | — |

**Důležité:** Tato tabulka musí být udržována aktuální při každém novém Epicu
(přidat do DoD všech budoucích Epiců).

---

## Definition of Done (Epic Level)

- [ ] `uv pip install -e .` funguje, všechny testy zelené
- [ ] Žádný soubor v repozitáři neobsahuje: "Mama AI", "Telma", "Adéla", "technické kolo"
- [ ] `src/examples/self_education/Agentni_systemy/` přejmenováno
- [ ] Root `README.md` přepsán jako veřejný projekt
- [ ] Srovnávací tabulka v README
- [ ] `ruff check` + `mypy --strict` zelené
- [ ] `uv run pytest -m "not integration"` zelený
- [ ] Všechny demo skripty spustitelné bez `agr()`
