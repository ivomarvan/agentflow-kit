"""Unit tests for LiveModel demo server endpoints."""

from __future__ import annotations

from typing import Annotated

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

from agentflow import AgentApp  # noqa: E402
from agentflow.events import StateUpdateEvent  # noqa: E402
from agentflow.gui.server import create_app  # noqa: E402
from agentflow.live_model import LiveModel, action  # noqa: E402


class _CounterState(BaseModel):
    model_config = ConfigDict(frozen=False)
    count: int = 0


class _CounterModel(LiveModel):
    """Minimal counter used as demo-server test fixture."""

    def __init__(self) -> None:
        self._state = _CounterState()

    @property
    def state(self) -> _CounterState:
        return self._state

    @action
    def increment(
        self,
        step: Annotated[int, Field(ge=1, le=100)] = 1,
    ) -> str:
        """Add step to the counter."""
        self._state.count += step
        return f"Counter is now {self._state.count}."

    @action
    def decrement(
        self,
        step: Annotated[int, Field(ge=1, le=100)] = 1,
    ) -> str:
        """Subtract step from the counter."""
        self._state.count = max(0, self._state.count - step)
        return f"Counter is now {self._state.count}."

    @action
    def reset(self) -> str:
        """Reset the counter to zero."""
        self._state.count = 0
        return "Counter reset to zero."


@pytest.fixture
def counter_app() -> AgentApp:
    """AgentApp wired with a CounterModel live_model."""
    return AgentApp(doc="Counter demo", live_model=_CounterModel())


@pytest.fixture
def bare_app() -> AgentApp:
    """AgentApp without live_model."""
    return AgentApp(doc="No model")


@pytest.fixture
def counter_fastapi(counter_app: AgentApp):  # type: ignore[no-untyped-def]
    """FastAPI app wrapping counter_app."""
    return create_app(counter_app)


@pytest.fixture
def bare_fastapi(bare_app: AgentApp):  # type: ignore[no-untyped-def]
    """FastAPI app without live_model."""
    return create_app(bare_app)


@pytest.mark.asyncio
async def test_demo_tools_returns_schema_list(counter_fastapi) -> None:  # type: ignore[no-untyped-def]
    async with AsyncClient(
        transport=ASGITransport(app=counter_fastapi), base_url="http://test"
    ) as client:
        response = await client.get("/api/demo/tools")
    assert response.status_code == 200
    tools = response.json()
    assert len(tools) == 3
    names = {tool["name"] for tool in tools}
    assert names == {"increment", "decrement", "reset"}
    increment = next(t for t in tools if t["name"] == "increment")
    assert "parameters" in increment
    assert increment["parameters"]["properties"]["step"]["type"] == "integer"


@pytest.mark.asyncio
async def test_demo_tools_no_model_returns_400(bare_fastapi) -> None:  # type: ignore[no-untyped-def]
    async with AsyncClient(
        transport=ASGITransport(app=bare_fastapi), base_url="http://test"
    ) as client:
        response = await client.get("/api/demo/tools")
    assert response.status_code == 400
    assert response.json() == {"error": "No live_model registered"}


@pytest.mark.asyncio
async def test_demo_action_increment_returns_result(counter_fastapi) -> None:  # type: ignore[no-untyped-def]
    async with AsyncClient(
        transport=ASGITransport(app=counter_fastapi), base_url="http://test"
    ) as client:
        response = await client.post("/api/demo/action/increment", json={"step": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None
    assert "5" in data["result"]


@pytest.mark.asyncio
async def test_demo_action_updates_live_state(counter_fastapi, counter_app: AgentApp) -> None:  # type: ignore[no-untyped-def]
    async with AsyncClient(
        transport=ASGITransport(app=counter_fastapi), base_url="http://test"
    ) as client:
        await client.post("/api/demo/action/increment", json={"step": 3})
        response = await client.get("/api/live-state")
    assert response.status_code == 200
    data = response.json()
    assert data["has_live_state"] is True
    assert data["state_data"]["count"] == 3
    assert counter_app._live_state.count == 3  # noqa: SLF001


@pytest.mark.asyncio
async def test_demo_action_unknown_tool_returns_404(counter_fastapi) -> None:  # type: ignore[no-untyped-def]
    async with AsyncClient(
        transport=ASGITransport(app=counter_fastapi), base_url="http://test"
    ) as client:
        response = await client.post("/api/demo/action/nonexistent", json={})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_demo_action_emits_state_update_event(counter_app: AgentApp) -> None:  # type: ignore[no-untyped-def]
    received: list[StateUpdateEvent] = []

    class _Collector:
        async def on_event(self, event: StateUpdateEvent) -> None:
            if isinstance(event, StateUpdateEvent):
                received.append(event)

    counter_app.event_bus.subscribe(_Collector())
    fastapi_app = create_app(counter_app)
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as client:
        await client.post("/api/demo/action/increment", json={"step": 2})
    assert len(received) == 1
    assert received[0].state_data["count"] == 2


@pytest.mark.unit
def test_agentapp_live_model_sets_live_state() -> None:
    model = _CounterModel()
    app = AgentApp(live_model=model)
    assert app._live_state is model.state  # noqa: SLF001
    assert app._live_model is model  # noqa: SLF001
