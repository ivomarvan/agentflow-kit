"""FastAPI application factory for the agentflow GUI server.

Exposes a REST + WebSocket API that wraps a single ``AgentApp`` instance:

    REST endpoints:
        GET  /health        — liveness probe
        GET  /api/info      — script title and module doc (tooltip)
        GET  /api/schema    — JSON Schema of configurable parameters
        GET  /api/config    — current config values (dot-path dict)
        POST /api/config    — set a single config value
        POST /api/run       — start a workflow run (returns run_id)
        GET  /api/samples   — list of example prompts
        GET  /api/graph     — interactive HTML graph (same as ``graph --browser``)
        GET  /api/source    — syntax-highlighted Python source (tooltip file links)

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
import contextlib
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
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
        terminal_events: Buffers the final JSON payload for each completed run so
            that a WebSocket client which connects after the run finishes still
            receives the terminal event.  Entries are keyed by run_id and
            retained for the lifetime of the server (memory is negligible).
        run_events: Buffers ALL event payloads emitted during a run (keyed by
            run_id) so that a late-joining WebSocket client receives a full
            replay of every event, not only the terminal one.
    """

    active_run_id: str | None = None
    is_running: bool = False
    ws_clients: dict[str, list[WebSocket]] = field(default_factory=dict)
    terminal_events: dict[str, dict] = field(default_factory=dict)
    run_events: dict[str, list[dict]] = field(default_factory=dict)


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


class TtsRequest(BaseModel):
    """Request body for POST /api/tts."""

    text: str
    voice: str = "Kore"
    lang: str = "en-US"


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

    if getattr(agent_app, "_live_model", None) is not None:
        demo_handler = WebSocketEventHandler("demo", app.state.run_state)
        agent_app.event_bus.subscribe(demo_handler)

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
        """Return GUI header title and module docstring for the title tooltip.

        Returns:
            Dict with ``name`` (script stem when launched via CLI, else class name)
            and ``doc`` (entry-point module docstring, Markdown).
        """
        agent = app.state.agent_app
        name = getattr(agent, "gui_script_name", "") or agent.name
        doc = getattr(agent, "gui_script_doc", "") or getattr(agent, "_doc", "") or ""
        return {"name": name, "doc": doc}

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
        run_state.ws_clients[run_id] = []
        run_state.run_events[run_id] = []  # pre-create buffer for ws_hooks

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

    @app.get("/api/live-state")
    async def live_state_info() -> dict[str, Any]:
        """Return the initial live-state schema and data if the agent has live_state.

        Called once on GUI mount so the StateViewerPanel populates immediately
        (before the first run) rather than waiting for the first StateUpdateEvent.

        Returns:
            ``{"has_live_state": False}`` when the agent has no live_state model.
            Otherwise ``{"has_live_state": True, "display_schema": ..., "state_data": ...}``.
        """
        agent_app: AgentApp = app.state.agent_app
        live = getattr(agent_app, "_live_state", None)
        if live is None or not hasattr(live, "model_dump"):
            return {"has_live_state": False}
        from agentflow.gui.state_viewer import extract_display_schema  # noqa: PLC0415

        return {
            "has_live_state": True,
            "display_schema": extract_display_schema(type(live)),
            "state_data": live.model_dump(),
        }

    @app.get("/api/demo/tools")
    async def demo_tools() -> Any:
        """Return @action tool schemas for the demo ActionPanel.

        Returns:
            JSON list of tool schema dicts when ``live_model`` is registered.

        Raises:
            HTTPException: 400 when the agent has no ``live_model``.
        """
        agent_app: AgentApp = app.state.agent_app
        live_model = getattr(agent_app, "_live_model", None)
        if live_model is None:
            return JSONResponse(
                status_code=400,
                content={"error": "No live_model registered"},
            )
        from agentflow.gui.demo_server import list_demo_tools  # noqa: PLC0415

        return list_demo_tools(live_model)

    @app.post("/api/demo/action/{tool_name}")
    async def demo_action(tool_name: str, request: Request) -> Any:
        """Execute one @action tool and push updated live state to the event bus.

        Args:
            tool_name: Registered tool name.
            request: Raw request — body must be a JSON object of parameters.

        Returns:
            ``{"result": ..., "error": null}`` on success, or error payload when
            the tool reports failure.

        Raises:
            HTTPException: 400 for invalid JSON; 404 for unknown tool.
        """
        agent_app: AgentApp = app.state.agent_app
        live_model = getattr(agent_app, "_live_model", None)
        if live_model is None:
            return JSONResponse(
                status_code=400,
                content={"error": "No live_model registered"},
            )
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        registry = live_model.tool_registry()
        if registry.get(tool_name) is None:
            raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")

        from agentflow.gui.demo_server import execute_demo_action  # noqa: PLC0415

        return await execute_demo_action(agent_app, tool_name, body)

    @app.get("/api/tts/voices")
    async def tts_voices() -> list[dict[str, str]]:
        """Return the list of available Gemini TTS voices.

        Returns:
            List of ``{"name": ..., "label": ...}`` dicts.
        """
        from agentflow.gui.tts_service import GEMINI_VOICES
        return GEMINI_VOICES

    @app.post("/api/tts")
    async def tts(body: TtsRequest) -> Response:
        """Synthesise speech via Gemini TTS and return MP3 audio.

        Results are cached on disk so repeated requests for the same
        (text, voice, lang) tuple are served without API calls.

        Args:
            body: Contains ``text``, ``voice`` (Gemini voice name), and
                  ``lang`` (BCP-47 language code).

        Returns:
            MP3 audio bytes with ``Content-Type: audio/mpeg``.

        Raises:
            HTTPException 503: If ``GEMINI_API_KEY`` is missing.
            HTTPException 502: If the Gemini API call fails.
        """
        from agentflow.gui.tts_service import GeminiTtsService
        try:
            service = GeminiTtsService()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        try:
            audio = await service.synthesize(
                text=body.text, voice=body.voice, lang=body.lang
            )
        except Exception as exc:
            logger.error("Gemini TTS error: %s", exc)
            raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {exc}") from exc
        return Response(content=audio, media_type="audio/wav")

    @app.get("/api/graph")
    async def graph(request: Request) -> HTMLResponse:
        """Return the agent composition graph as interactive HTML.

        Interactive graph HTML (tooltips); no duplicate page header (``with_title=False``).
        Tooltip ``file`` links point at ``/api/source`` so they work inside the GUI iframe.

        Returns:
            Complete HTML document from ``Describable.get_graph_html()``.

        Raises:
            HTTPException 503: If graphviz is not installed.
        """
        agent = app.state.agent_app
        title = getattr(agent, "gui_script_name", "") or agent.name
        base = str(request.base_url).rstrip("/")
        try:
            html = agent.get_graph_html(
                title=title,
                with_title=False,
                source_link_base=f"{base}/api/source",
            )
        except ImportError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return HTMLResponse(content=html, media_type="text/html; charset=utf-8")

    @app.get("/api/source")
    async def source(path: str, line: int | None = None) -> HTMLResponse:
        """Return a Python source file as syntax-highlighted HTML.

        Used by graph tooltip ``file`` links in the GUI Structure tab.  Only paths
        under allowed roots (cwd, ``sys.path``, ``agentflow`` package) are served.

        Args:
            path: Absolute or relative path to a ``.py`` file.
            line: Optional 1-based line number to highlight and scroll into view.

        Returns:
            Standalone HTML page with Pygments highlighting and line numbers.

        Raises:
            HTTPException 400: Invalid path or non-Python file.
            HTTPException 403: Path outside allowed roots.
            HTTPException 404: File not found.
        """
        from agentflow.gui.source_viewer import render_source_html, resolve_source_path

        try:
            resolved = resolve_source_path(path)
            html = render_source_html(resolved, line=line)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return HTMLResponse(content=html, media_type="text/html; charset=utf-8")

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    @app.websocket("/ws/demo")
    async def demo_websocket_endpoint(websocket: WebSocket) -> None:
        """Stream live-model demo events (StateUpdateEvent) to the ActionPanel GUI."""
        await websocket_endpoint(websocket, "demo")

    @app.websocket("/ws/{run_id}")
    async def websocket_endpoint(websocket: WebSocket, run_id: str) -> None:
        """Accept a WebSocket connection and stream events for *run_id*.

        The client should connect before or shortly after POST /api/run.
        The server sends a ``ping`` frame every 30 s to keep the connection
        alive; clients should respond with ``{"type": "ping"}``.

        If the run already finished before the client connected (race condition
        for fast synchronous workflows), the buffered terminal event is delivered
        immediately after the handshake so the client does not spin forever.

        Args:
            websocket: The WebSocket connection from FastAPI.
            run_id: The run identifier to subscribe to.
        """
        await websocket.accept()
        run_state: RunState = app.state.run_state
        if run_id not in run_state.ws_clients:
            run_state.ws_clients[run_id] = []
        run_state.ws_clients[run_id].append(websocket)

        # Replay all buffered events when the workflow already produced some or all
        # of its events before this WebSocket was established (race condition for
        # fast synchronous workflows — question_sent, step_start/end, run_complete
        # may all arrive before the browser finishes the WebSocket handshake).
        for payload in run_state.run_events.get(run_id, []):
            try:
                await websocket.send_json(payload)
            except Exception:
                break  # connection broken during replay — stop sending

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
    # Demo page — same SPA as / but frontend reads ?mode=demo from path
    # ------------------------------------------------------------------

    @app.get("/demo")
    async def demo_page() -> FileResponse:
        """Serve the Vue SPA for LiveModel standalone demo mode."""
        index = STATIC_DIR / "index.html"
        if not index.exists():
            raise HTTPException(status_code=503, detail="GUI static build not found")
        return FileResponse(index)

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

    The function yields to the event loop before starting (``asyncio.sleep(0)``)
    to allow any pending WebSocket upgrade requests to be processed first,
    preventing a race condition where fast synchronous workflows complete before
    the client's WebSocket connection is accepted.

    Args:
        app: The FastAPI application (for accessing ``app.state``).
        run_id: Unique identifier for this run.
        prompt: User prompt forwarded to ``run_workflow_with_prompt()``.
        ws_handler: Handler to unsubscribe after the run.
    """
    from agentflow.events import QuestionSentEvent, RunCompleteEvent, RunErrorEvent
    from agentflow.gui.log_handler import EventBusLoggingHandler

    agent_app: AgentApp = app.state.agent_app
    run_state: RunState = app.state.run_state

    # Yield to the event loop so any pending WebSocket upgrade request for
    # this run_id is accepted before we emit the terminal event.
    await asyncio.sleep(0)

    # Route Python log messages from the agentflow namespace and all application
    # loggers into the event stream.  Adding only to root_logger is sufficient:
    # all child loggers (agentflow.*, examples.*) propagate to root by default,
    # so a single handler on root_logger avoids double-logging.
    log_handler = EventBusLoggingHandler(agent_app.event_bus, level=logging.DEBUG)
    log_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)

    try:
        # Announce the question so the event log shows it clearly.
        await agent_app.event_bus.emit(
            QuestionSentEvent(run_id=run_id, question=prompt or "(empty)")
        )
        result = await agent_app.run_workflow_with_prompt(prompt)
        last_ctx = getattr(agent_app, "_last_ctx", None)
        is_error = bool(last_ctx is not None and last_ctx.run_errors)
        event = RunCompleteEvent(run_id=run_id, result=result, is_error=is_error)
        await agent_app.event_bus.emit(event)
        # Buffer the terminal payload so late-connecting WS clients still
        # receive it (race condition for fast synchronous workflows).
        run_state.terminal_events[run_id] = {
            "type": "run_complete",
            "run_id": run_id,
            **event.model_dump(exclude={"run_id", "event_type"}, mode="json"),
        }

        # Emit run statistics AFTER run_complete so they appear last in the
        # event log (user sees stats below the DONE line, always visible).
        last_ctx = getattr(agent_app, "_last_ctx", None)
        if last_ctx is not None:
            from agentflow.events import RunStatsEvent  # noqa: PLC0415
            s = last_ctx.stats
            elapsed_ms = getattr(last_ctx, "_run_elapsed_ms", 0.0)
            await agent_app.event_bus.emit(RunStatsEvent(
                run_id=run_id,
                elapsed_ms=elapsed_ms,
                total_tokens=s.total_tokens,
                prompt_tokens=s.prompt_tokens,
                completion_tokens=s.completion_tokens,
                llm_calls=s.llm_calls,
                cache_hits=s.cache_hits,
                by_model=dict(s.by_model),
            ))
    except Exception as exc:
        logger.exception("Workflow run_id=%s failed: %s", run_id, exc)
        event = RunErrorEvent(run_id=run_id, message=str(exc))
        await agent_app.event_bus.emit(event)
        run_state.terminal_events[run_id] = {
            "type": "run_error",
            "run_id": run_id,
            **event.model_dump(exclude={"run_id", "event_type"}, mode="json"),
        }
    finally:
        root_logger.removeHandler(log_handler)
        app.state.run_state.is_running = False
        with contextlib.suppress(ValueError):
            agent_app.event_bus.unsubscribe(ws_handler)


# ---------------------------------------------------------------------------
# serve() — entry-point for cli() and direct usage
# ---------------------------------------------------------------------------


def serve(
    agent_app: AgentApp,
    *,
    port: int | None = None,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    demo_url_path: str = "",
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
        demo_url_path: Optional path suffix (e.g. ``"/demo"``) appended to the
            opened browser URL for LiveModel standalone demos.
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
        url = f"http://{host}:{resolved_port}{demo_url_path}"
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
