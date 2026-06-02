---
apm_category: epic-plan
apm_ref: E097
apm_level: epic
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-05-30
updated_at: 2026-05-30
approved_by: Human
approved_at: 2026-05-30
---

# Epic E097 — FastAPI backend + WebSocket + `gui` CLI subcommand

**Cíl:** Implementovat `agentflow.gui` jako volitelný Python balíček (`agentflow[gui]`).
FastAPI server přijímá instanci `AgentApp`, exponuje REST + WebSocket API pro Chat,
config schema a graf. `AgentApp.cli()` dostane nový subcommand `gui` — spustí server
a otevře prohlížeč.

---

## Scope

| Oblast | Co se mění |
|--------|-----------|
| `pyproject.toml` | `[project.optional-dependencies] gui = [...]` |
| `agentflow/gui/__init__.py` (nový pkg) | Public API: `GuiServer`, `serve()` |
| `agentflow/gui/server.py` (nový) | FastAPI app factory `create_app(agent_app)` |
| `agentflow/gui/ws_hooks.py` (nový) | `WebSocketEventHandler` + `WebSocketHooks` |
| `agentflow/gui/build.py` (nový) | Build check + `npm run build` wrapper |
| `agentflow/app.py` | Přidat `gui` subcommand do `cli()` |
| `docker-compose.yml` | Compose profile `gui` (optional) |
| `README.docker.md` | Sekce: GUI v Dockeru |

---

## Task List

| Task | Název | Závisí na |
|------|-------|-----------|
| T010 | pyproject.toml extras + `agentflow/gui/` package skeleton | E096 |
| T020 | FastAPI app factory + REST endpointy | T010 |
| T030 | WebSocket event streaming + `WebSocketEventHandler` | T020 |
| T040 | Build check + `gui` subcommand v `AgentApp.cli()` | T030 |

---

## T010 — Package skeleton + závislosti

### `pyproject.toml`

```toml
[project.optional-dependencies]
gui = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",   # [standard] includes websockets + httptools
    "websockets>=12.0",
]
```

Instalace: `uv pip install -e ".[gui]"`

### Adresářová struktura

```
agentflow/gui/
    __init__.py          # GuiServer, serve()
    server.py            # create_app(agent_app: AgentApp) -> FastAPI
    ws_hooks.py          # WebSocketEventHandler
    build.py             # check_build(), ensure_build()
    static/              # prázdný placeholder — gui/dist se kopíruje sem při buildu
        .gitkeep
```

### `agentflow/gui/__init__.py`

```python
"""Optional GUI package for agentflow. Install with: pip install agentflow[gui]

Usage:
    from agentflow.gui import serve
    from my_app import MyApp

    serve(MyApp())   # starts FastAPI + opens browser
"""
from agentflow.gui.server import GuiServer, serve

__all__ = ["GuiServer", "serve"]
```

---

## T020 — FastAPI REST endpointy

### `agentflow/gui/server.py`

```python
def create_app(agent_app: AgentApp) -> FastAPI:
    """Create a FastAPI application for the given AgentApp instance."""
    ...
```

**REST endpointy:**

```
GET  /api/info              → {name, description, version}
GET  /api/schema            → JSON Schema (AgentApp.get_config_schema())
GET  /api/config            → current config values (AgentApp.get_config())
POST /api/config            → body: {path: str, value: Any} → set_config()
POST /api/run               → body: {prompt: str} → spustí workflow (run_id v response)
GET  /api/samples           → list[str] (AgentApp.sample_prompts)
GET  /api/graph             → SVG string (AgentApp.get_graph() → render SVG)
GET  /health                → {"status": "ok"}
```

**Statické soubory:**
```python
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
```

`STATIC_DIR` = `agentflow/gui/static/` (pre-built Vue SPA).

**Session / run management:**
- Jeden aktivní běh najednou; druhý `POST /api/run` vrátí HTTP 409 pokud běh probíhá
- `run_id` generován serverem (`uuid4().hex`)
- Výsledek běhu uložen v paměti pro daný `run_id` (dict, max 100 záznamů)

---

## T030 — WebSocket event streaming

### WebSocket endpoint

```
WS  /ws/{run_id}            → event stream pro daný běh
WS  /ws/log                 → continuous log stream (bez run_id)
```

### WebSocket message protocol (JSON)

```json
// Server → Client
{"type": "step_start",    "vertex": "Research", "step": 2, "run_id": "abc123"}
{"type": "step_end",      "vertex": "Research", "step": 2, "signal": "ok"}
{"type": "log",           "level": "INFO", "message": "Fetching...", "logger": "statemachine"}
{"type": "domain_event",  "event_type": "hotel.reservation", "data": {...}}
{"type": "run_complete",  "result": "Report published.", "run_id": "abc123"}
{"type": "run_error",     "message": "LLM timeout", "run_id": "abc123"}

// Client → Server
{"type": "ping"}
```

### `WebSocketEventHandler`

```python
class WebSocketEventHandler:
    """Forwards AgentEvents to a WebSocket connection as JSON messages."""

    def __init__(self, websocket: WebSocket) -> None: ...

    async def on_event(self, event: AgentEvent) -> None:
        payload = {"type": event.event_type.split(".")[-1], **event.model_dump()}
        await self.websocket.send_json(payload)
```

Registrace: při `POST /api/run` se `WebSocketEventHandler` připojí k `EventBus` běhu,
po dokončení se odpojí.

**Broadcast:** Jeden běh → broadcast do všech WS klientů připojených na `/ws/{run_id}`.
Implementace: `dict[run_id, list[WebSocket]]` na `FastAPI.state`.

---

## T040 — Build check + `gui` subcommand

### `agentflow/gui/build.py`

```python
DIST_DIR = Path(__file__).parent / "static"
DIST_INDEX = DIST_DIR / "index.html"

def check_build() -> tuple[bool, str]:
    """Check if pre-built GUI is present and up-to-date.

    Returns:
        (ok: bool, message: str)
    """
    if not DIST_INDEX.exists():
        return False, "GUI not built. Run: cd gui && npm run build"
    return True, "ok"

def ensure_build(*, force: bool = False, interactive: bool = True) -> None:
    """Ensure GUI is built; prompt user if outdated."""
    ...
```

### `AgentApp.cli()` — nový subcommand `gui`

```python
# V run_argparse() dispatch:
elif args.command == "gui":
    from agentflow.gui import serve
    serve(self, port=getattr(args, "port", None), host=getattr(args, "host", "127.0.0.1"))
```

CLI help (top-level subcommands on `AgentApp.cli()`):
```
script.py -h
script.py run [QUESTION...]
script.py gui [--host HOST] [--port PORT] [--no-browser]
    Start local GUI server and open in browser.
    Default port: 8765 (override via AGENTFLOW_GUI_PORT env var or --port)
script.py describe [--format markdown|json|html] [-o FILE]
script.py graph [--format dot|svg|svg-raw|html|png] [-o FILE]
script.py graph --browser
```

Port priority: default `8765` → `AGENTFLOW_GUI_PORT` env var → `--port` CLI arg.

### `GuiServer.serve()`

```python
def serve(
    agent_app: AgentApp,
    *,
    port: int | None = None,
    host: str = "127.0.0.1",
    open_browser: bool = True,
) -> None:
    """Start uvicorn server; optionally open browser."""
    resolved_port = port or int(os.getenv("AGENTFLOW_GUI_PORT", "8765"))
    ensure_build(interactive=True)
    app = create_app(agent_app)
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{resolved_port}")).start()
    uvicorn.run(app, host=host, port=resolved_port)
```

### Docker compose profile (dokumentace)

```yaml
# docker-compose.yml — přidat profile:
services:
  app-gui:
    profiles: ["gui"]
    build: .
    ports:
      - "8765:8765"
    environment:
      AGENTFLOW_GUI_PORT: "8765"
    command: uv run python examples/quickstart/04_parallel_research_loop.py gui --host 0.0.0.0 --no-browser
```

---

## Epic E097 Definition of Done

- [ ] `pip install agentflow[gui]` nainstaluje FastAPI + uvicorn
- [ ] `python script.py gui` spustí server na portu 8765 a otevře browser
- [ ] `GET /api/info` vrátí jméno a popis AgentApp
- [ ] `POST /api/run` spustí workflow; `GET /ws/{run_id}` stream events
- [ ] `GET /api/schema` vrátí JSON Schema (z E096)
- [ ] HTTP 409 pro souběžný `POST /api/run`
- [ ] Build check s interaktivní otázkou při zastaralém buildu
- [ ] Port: default 8765, přetěžitelný env / CLI
- [ ] `docker-compose.yml` profile `gui` zdokumentován
- [ ] Unit testy: REST endpointy (`httpx.AsyncClient`), WS mock

## Poznámky pro Codera

- FastAPI `lifespan` context manager pro inicializaci `agent_app`
- `StaticFiles` montovat na `/` až po registraci všech API routes (pořadí záleží)
- `uvicorn.run()` blokuje — `threading.Timer` pro otevření browseru PŘED `uvicorn.run()`
- Pro testy: `from httpx import AsyncClient` s `transport=ASGITransport(app=...)`
