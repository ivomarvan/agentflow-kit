"""FastAPI application factory for the agentflow GUI server.

Exposes a REST + WebSocket API that wraps a single ``AgentApp`` instance:

    REST endpoints:
        GET  /health        — liveness probe
        GET  /api/info      — app name and class
        GET  /api/schema    — JSON Schema of configurable parameters
        GET  /api/config    — current config values (dot-path dict)
        POST /api/config    — set a single config value
        POST /api/run       — start a workflow run (returns run_id)
        GET  /api/samples   — list of example prompts
        GET  /api/graph     — raw SVG of the agent composition graph

    WebSocket endpoint:
        WS   /ws/{run_id}   — event stream for a specific run

Factory usage::

    from agentflow.gui.server import create_app, serve
    from my_app import MyApp

    app = create_app(MyApp())          # for ASGI / testing
    serve(MyApp())                     # starts uvicorn + opens browser
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agentflow.gui.build import STATIC_DIR
from agentflow.gui.ws_hooks import WebSocketEventHandler

if TYPE_CHECKING:
    from agentflow.app import AgentApp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Run state — one instance per FastAPI app, stored on app.state
# ---------------------------------------------------------------------------


@dataclass
class RunState:
    """Mutable server state tracking the active workflow run and WS clients.

    Attributes:
        active_run_id: hex run_id of the currently active run, or None.
        is_running: True while a workflow is executing.
        ws_clients: Maps run_id to the list of connected WebSocket objects.
    """

    active_run_id: str | None = None
    is_running: bool = False
    ws_clients: dict[str, list[WebSocket]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class ConfigSetRequest(BaseModel):
    """Request body for POST /api/config."""

    path: str
    value: Any


class RunRequest(BaseModel):
    """Request body for POST /api/run."""

    prompt: str = ""


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(agent_app: AgentApp) -> FastAPI:
    """Create and configure a FastAPI application for *agent_app*.

    Registers all REST endpoints, the WebSocket endpoint, CORS middleware,
    and mounts the static Vue SPA last so API routes take precedence.

    Args:
        agent_app: The ``AgentApp`` instance whose workflow this server exposes.

    Returns:
        Configured ``FastAPI`` application (ASGI-compatible).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[type-arg]
        """Lifespan hook — state is already set eagerly; reserved for future use."""
        yield

    app = FastAPI(
        title=type(agent_app).__name__,
        description="agentflow GUI server",
        lifespan=lifespan,
    )

    # Initialise state eagerly so it is available without lifespan trigger
    # (required for ASGI test clients that skip the lifespan protocol).
    app.state.agent_app = agent_app
    app.state.run_state = RunState()

    # CORS — allow the Vite dev server and the default production port
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8765"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Return a simple liveness response.

        Returns:
            ``{"status": "ok"}``
        """
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # Info / schema / config
    # ------------------------------------------------------------------

    @app.get("/api/info")
    async def info() -> dict[str, str]:
        """Return the agent app's name and class.

        Returns:
            Dict with ``name`` (description) and ``description`` (class name).
        """
        return {
            "name": app.state.agent_app.name,
            "description": app.state.agent_app.description or type(app.state.agent_app).__name__,
        }

    @app.get("/api/schema")
    async def schema() -> dict[str, Any]:
        """Return the JSON Schema for all configurable parameters.

        Returns:
            JSON-Schema-compatible dict produced by ``AgentApp.get_config_schema()``.
        """
        return app.state.agent_app.get_config_schema()

    @app.get("/api/config")
    async def get_config() -> dict[str, Any]:
        """Return current values of all configurable parameters.

        Returns:
            Flat dot-path dict produced by ``AgentApp.get_config()``.
        """
        return app.state.agent_app.get_config()

    @app.post("/api/config")
    async def set_config(body: ConfigSetRequest) -> dict[str, str]:
        """Set a single configurable parameter by dot-path.

        Args:
            body: Contains ``path`` (e.g. ``"connector.model"``) and ``value``.

        Returns:
            ``{"status": "ok"}`` on success.

        Raises:
            HTTPException 400: If the path is invalid or value fails validation.
        """
        try:
            app.state.agent_app.set_config(body.path, body.value)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    @app.post("/api/run")
    async def start_run(body: RunRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
        """Start a workflow run in the background.

        Only one run may be active at a time; a second call returns HTTP 409.

        Args:
            body: Contains the ``prompt`` string forwarded to the workflow.

        Returns:
            ``{"run_id": str, "status": "started"}``

        Raises:
            HTTPException 409: When a run is already in progress.
        """
        run_state: RunState = app.state.run_state
        if run_state.is_running:
            raise HTTPException(status_code=409, detail="A run is already in progress")

        run_id = uuid.uuid4().hex
        run_state.active_run_id = run_id
        run_state.is_running = True

        ws_handler = WebSocketEventHandler(run_id, run_state)
        app.state.agent_app.event_bus.subscribe(ws_handler)

        background_tasks.add_task(_run_workflow, app, run_id, body.prompt, ws_handler)
        return {"run_id": run_id, "status": "started"}

    @app.get("/api/samples")
    async def samples() -> list[str]:
        """Return the list of example prompts for this agent.

        Returns:
            List of prompt strings from ``AgentApp.sample_prompts``.
        """
        return app.state.agent_app.sample_prompts

    @app.get("/api/graph")
    async def graph() -> str:
        """Return the agent composition graph as a raw SVG string.

        Returns:
            SVG XML string rendered by Graphviz via ``GraphRenderer.to_svg()``.

        Raises:
            HTTPException 503: If graphviz is not installed.
        """
        from agentflow.describable.graph_renderer import GraphRenderer

        try:
            svg = GraphRenderer.to_svg(app.state.agent_app.get_graph())
        except ImportError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return svg

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    @app.websocket("/ws/{run_id}")
    async def websocket_endpoint(websocket: WebSocket, run_id: str) -> None:
        """Accept a WebSocket connection and stream events for *run_id*.

        The client should connect before or shortly after POST /api/run.
        The server sends a ``ping`` frame every 30 s to keep the connection
        alive; clients should respond with ``{"type": "ping"}``.

        Args:
            websocket: The WebSocket connection from FastAPI.
            run_id: The run identifier to subscribe to.
        """
        await websocket.accept()
        run_state: RunState = app.state.run_state
        if run_id not in run_state.ws_clients:
            run_state.ws_clients[run_id] = []
        run_state.ws_clients[run_id].append(websocket)
        try:
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                    if data == '{"type":"ping"}':
                        await websocket.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            clients = run_state.ws_clients.get(run_id, [])
            if websocket in clients:
                clients.remove(websocket)

    # ------------------------------------------------------------------
    # Static files — must be LAST so API routes take priority
    # ------------------------------------------------------------------

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_workflow(
    app: FastAPI,
    run_id: str,
    prompt: str,
    ws_handler: WebSocketEventHandler,
) -> None:
    """Execute the agent workflow in the background.

    Emits ``RunCompleteEvent`` on success or ``RunErrorEvent`` on failure.
    Clears ``RunState.is_running`` and unsubscribes *ws_handler* in all cases.

    Args:
        app: The FastAPI application (for accessing ``app.state``).
        run_id: Unique identifier for this run.
        prompt: User prompt forwarded to ``run_workflow_with_prompt()``.
        ws_handler: Handler to unsubscribe after the run.
    """
    from agentflow.events import RunCompleteEvent, RunErrorEvent

    agent_app: AgentApp = app.state.agent_app
    try:
        result = await agent_app.run_workflow_with_prompt(prompt)
        await agent_app.event_bus.emit(RunCompleteEvent(run_id=run_id, result=result))
    except Exception as exc:
        logger.exception("Workflow run_id=%s failed: %s", run_id, exc)
        await agent_app.event_bus.emit(RunErrorEvent(run_id=run_id, message=str(exc)))
    finally:
        app.state.run_state.is_running = False
        try:
            agent_app.event_bus.unsubscribe(ws_handler)
        except ValueError:
            pass  # already removed


# ---------------------------------------------------------------------------
# serve() — entry-point for cli() and direct usage
# ---------------------------------------------------------------------------


def serve(
    agent_app: AgentApp,
    *,
    port: int | None = None,
    host: str = "127.0.0.1",
    open_browser: bool = True,
) -> None:
    """Start FastAPI + uvicorn for the given AgentApp; optionally open browser.

    ``uvicorn.run()`` blocks until the server is stopped.  The browser is
    opened via a short ``threading.Timer`` so it fires after the server is
    ready.

    Port resolution order: *port* argument → ``AGENTFLOW_GUI_PORT`` env var → 8765.

    Args:
        agent_app: The ``AgentApp`` instance to serve.
        port: Override port.  ``None`` falls back to env var or 8765.
        host: Bind address.  Defaults to ``127.0.0.1`` (localhost only).
        open_browser: When ``True``, open the browser after 1.5 s.
    """
    import os
    import threading
    import webbrowser

    import uvicorn

    from agentflow.gui.build import ensure_build

    resolved_port = port or int(os.getenv("AGENTFLOW_GUI_PORT", "8765"))
    ensure_build(interactive=True)
    fastapi_app = create_app(agent_app)

    if open_browser:
        url = f"http://{host}:{resolved_port}"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(fastapi_app, host=host, port=resolved_port, log_level="info")


# ---------------------------------------------------------------------------
# GuiServer — thin wrapper kept for public API compatibility
# ---------------------------------------------------------------------------


class GuiServer:
    """Thin wrapper around ``serve()`` for object-oriented usage.

    Prefer the module-level ``serve()`` function for direct use.
    This class exists for backward API compatibility and for use-cases
    that need to hold server configuration as an object.

    Args:
        agent_app: The ``AgentApp`` instance to serve.
        port: Optional port override.
        host: Bind address.
        open_browser: Whether to open the browser on start.
    """

    def __init__(
        self,
        agent_app: AgentApp,
        *,
        port: int | None = None,
        host: str = "127.0.0.1",
        open_browser: bool = True,
    ) -> None:
        self._agent_app = agent_app
        self._port = port
        self._host = host
        self._open_browser = open_browser

    def serve(self) -> None:
        """Start the server (blocks until stopped).

        Delegates to the module-level ``serve()`` function.
        """
        serve(
            self._agent_app,
            port=self._port,
            host=self._host,
            open_browser=self._open_browser,
        )
