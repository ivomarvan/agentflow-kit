"""Unit tests for agentflow.gui.server using httpx AsyncClient.

Tests are skipped automatically when fastapi or httpx are not installed.
All tests run against an in-process ASGI app — no real HTTP port is bound.
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from agentflow import AgentApp  # noqa: E402
from agentflow.gui.server import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Test app fixture
# ---------------------------------------------------------------------------


class _SimpleTestApp(AgentApp):
    """Minimal AgentApp that returns a fixed string from run_workflow."""

    async def run_workflow(self) -> str | None:
        """Return a fixed test result."""
        return "test result"


@pytest.fixture
def test_app() -> _SimpleTestApp:
    """Return a fresh _SimpleTestApp instance."""
    return _SimpleTestApp()


@pytest.fixture
def fastapi_app(test_app: _SimpleTestApp):  # type: ignore[return]
    """Return a configured FastAPI app wrapping test_app."""
    return create_app(test_app)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_ok(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """GET /health returns {"status": "ok"}."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_info_contains_name(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/info returns name and doc keys."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.get("/api/info")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "_SimpleTestApp"
    assert "doc" in data
    assert isinstance(data["doc"], str)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_returns_interactive_html(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/graph returns standalone HTML with tooltip scripts."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.get("/api/graph")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert "marked" in body
    assert "svg-wrap" in body
    assert 'id="header"' not in body
    assert "http://test/api/source?path=" in body


@pytest.mark.asyncio
async def test_source_returns_highlighted_html(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/source returns Pygments HTML for an allowed project file."""
    from pathlib import Path

    source_path = Path(__file__).resolve()
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.get(
            "/api/source",
            params={"path": str(source_path), "line": 1},
        )
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert "<!DOCTYPE html>" in body
    assert "L1" in body
    assert str(source_path) in body


@pytest.mark.asyncio
async def test_source_rejects_disallowed_path(fastapi_app, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """GET /api/source returns 403 for paths outside allowed roots."""
    secret = tmp_path / "secret.py"
    secret.write_text("x = 1\n", encoding="utf-8")
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.get("/api/source", params={"path": str(secret)})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_samples_empty_by_default(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/samples returns [] when sample_prompts is not overridden."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.get("/api/samples")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_returns_dict(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/schema returns a JSON-Schema-compatible dict."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.get("/api/schema")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_returns_dict(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/config returns a dict (empty for apps with no connectors)."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.get("/api/config")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


@pytest.mark.asyncio
async def test_config_set_invalid_path_returns_400(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """POST /api/config with an invalid dot-path returns HTTP 400."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.post("/api/config", json={"path": "no_dot", "value": "x"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Run — 409 when busy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_returns_409_when_already_running(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """POST /api/run returns HTTP 409 when a run is already in progress."""
    fastapi_app.state.run_state.is_running = True
    try:
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app), base_url="http://test"
        ) as client:
            r = await client.post("/api/run", json={"prompt": "test"})
        assert r.status_code == 409
        assert "already in progress" in r.json()["detail"].lower()
    finally:
        fastapi_app.state.run_state.is_running = False


# ---------------------------------------------------------------------------
# Run — terminal event buffering (race condition for fast workflows)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_complete_is_buffered_when_workflow_finishes_before_ws_connects(
    fastapi_app,
) -> None:
    """RunCompleteEvent is stored in run_events after _run_workflow completes.

    This verifies the race-condition fix: fast synchronous workflows may finish
    and emit RunCompleteEvent before the browser WebSocket connects.  The server
    must buffer all events (including run_complete) so the WS endpoint can
    deliver a full replay on connect.
    """
    import asyncio
    import uuid
    from agentflow.gui.server import _run_workflow, RunState
    from agentflow.gui.ws_hooks import WebSocketEventHandler

    run_state: RunState = fastapi_app.state.run_state
    run_id = uuid.uuid4().hex
    run_state.ws_clients[run_id] = []
    run_state.run_events[run_id] = []
    ws_handler = WebSocketEventHandler(run_id, run_state)
    fastapi_app.state.agent_app.event_bus.subscribe(ws_handler)

    await _run_workflow(fastapi_app, run_id, "hello", ws_handler)

    buffered = run_state.run_events.get(run_id, [])
    assert buffered, "run_events must contain at least the run_complete entry"

    types = [e["type"] for e in buffered]
    assert "run_complete" in types, f"run_complete missing from buffered events: {types}"
    assert "question_sent" in types, f"question_sent missing from buffered events: {types}"

    # All payloads must be JSON-safe (no datetime objects)
    import json
    for payload in buffered:
        json.dumps(payload)  # raises TypeError if datetime was not converted


# ---------------------------------------------------------------------------
# Run — happy path (background task fires but we just check the response)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_starts_and_returns_run_id(fastapi_app) -> None:  # type: ignore[no-untyped-def]
    """POST /api/run returns run_id and status 'started' when not busy."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.post("/api/run", json={"prompt": "hello"})
    assert r.status_code == 200
    data = r.json()
    assert "run_id" in data
    assert data["status"] == "started"
    assert len(data["run_id"]) == 32  # uuid4().hex length
