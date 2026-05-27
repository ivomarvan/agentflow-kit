# ai_agents_education

Vzdělávací projekt pro pochopení agentic AI vzorů od základů.
Cílem je vlastní čistý framework — bez magie hotových knihoven — který odhaluje,
jak věci skutečně fungují pod kapotou.

## Struktura projektu

```
src/
├── lib/          vlastní LLM abstrakční knihovna
│   ├── llm/      konfigurace, konektory, Ollama
│   └── tools/    nástroje pro tool-calling
├── examples/     ukázkové skripty a experimenty
└── projects/     konkrétní projekty využívající knihovnu
```

## Nastavení prostředí

### Předpoklady

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) — doporučený správce prostředí (rychlý, moderní)

### Instalace `uv` (jednorázově)

```bash
pip install uv
```

### Vytvoření a naplnění prostředí

```bash
# vytvoří .venv a nainstaluje všechny závislosti z pyproject.toml
uv sync
```

Příkaz `uv sync` je idempotentní — pokud `.venv` existuje a je aktuální, nedělá nic.
Spusť ho vždy po `git pull` nebo při prvním klonování repozitáře.

### Aktivace prostředí

```bash
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows
```

Nebo spouštěj skripty přímo přes `uv run`:

```bash
uv run python src/agentflow/llm/LlmConfig.py show
```

### Alternativa: `venv` + `pip` (bez `uv`)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Konfigurace LLM

Zkopíruj `.env.example` do `.env` a doplň API klíče:

```bash
cp .env.example .env
```

Klíčové proměnné:

| Proměnná | Popis |
|---|---|
| `LLM_BACKEND` | `ollama` / `openai` / `gemini` / `deepseek` / `anthropic` |
| `LLM_MODEL` | název modelu (backend se auto-detekuje z prefixu) |
| `OPENAI_API_KEY` | klíč pro OpenAI |
| `GOOGLE_API_KEY` | klíč pro Gemini |
| `ANTHROPIC_API_KEY` | klíč pro Claude (Anthropic) |
| `DEEPSEEK_API_KEY` | klíč pro DeepSeek |

Výchozí backend je **Ollama** (lokální, bez klíče). Doporučený lehký model: `qwen2.5:1.5b`.

## Rychlý start

```bash
# Ověř konfiguraci
python src/agentflow/llm/LlmConfig.py show

# Otestuj spojení s LLM (ping)
python src/agentflow/llm/LlmConnector.py ping

# Správa lokálních Ollama modelů
python src/agentflow/llm/OllamaManager.py status

# Spusť ukázkový skript (ReAct agent s nástroji)
python src/examples/self_education/Agentni_systemy/my/02_tool_calling_demo.py

# Zobraz konfiguraci agenta (Markdown / JSON) bez volání LLM
python src/examples/self_education/Agentni_systemy/my/02_tool_calling_demo.py describe
python src/examples/self_education/Agentni_systemy/my/02_tool_calling_demo.py json
```

## Testování

### Unit testy — bez API klíčů, žádné síťové volání

```bash
pytest                   # výchozí — spustí pouze unit testy
pytest -m unit           # ekvivalentní explicitní volání
```

### Integrační testy — živá LLM API volání (platíte tokeny!)

```bash
pytest -m integration    # výchozí model: gpt-4o-mini (nejlevnější)
```

Integrační testy jsou **záměrně vynechány** z výchozího běhu (`addopts = "-m 'not integration'"`
v `pyproject.toml`). Spouštěj je jen ručně nebo v CI s nastaveným API klíčem.

```bash
# Jiný model/backend pro integrační testy:
TEST_LLM_BACKEND=gemini TEST_LLM_MODEL=gemini-2.0-flash pytest -m integration
```

### Struktura testů

```
tests/                   # projekt-level testy (budoucí e2e, příklady, …)
src/agentflow/tests/           # testy knihovny (přesunout spolu s lib při oddělení)
```

Obě složky jsou sbírány automaticky při každém `pytest`.
