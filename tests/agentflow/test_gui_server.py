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
    """GET /api/info returns a dict with a 'name' and 'description' key."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        r = await client.get("/api/info")
    assert r.status_code == 200
    data = r.json()
    assert "name" in data
    assert "description" in data
    assert data["name"] == "_SimpleTestApp"


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
