"""Demo-mode helpers for LiveModel standalone GUI (no LLM / state graph)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agentflow.events import StateUpdateEvent

if TYPE_CHECKING:
    from agentflow.app import AgentApp
    from agentflow.live_model import LiveModel


def list_demo_tools(live_model: LiveModel) -> list[dict[str, Any]]:
    """Build the tool schema list consumed by ``GET /api/demo/tools``.

    Args:
        live_model: LiveModel instance whose @action methods are exposed.

    Returns:
        List of dicts with ``name``, ``description``, and ``parameters`` keys.
    """
    tools: list[dict[str, Any]] = []
    for tool in live_model.tools():
        tools.append(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema(),
            }
        )
    return tools


async def execute_demo_action(
    agent_app: AgentApp,
    tool_name: str,
    body: dict[str, Any],
) -> dict[str, str | None]:
    """Run one @action tool and emit a StateUpdateEvent on the app event bus.

    Args:
        agent_app: AgentApp carrying ``_live_model`` and ``event_bus``.
        tool_name: Registered tool name (matches @action method name).
        body: JSON parameter object for the tool call.

    Returns:
        ``{"result": str | None, "error": str | None}`` — error set when the
        tool returns a string starting with ``"Error:"``.

    Raises:
        KeyError: When *tool_name* is not registered on the live model.
    """
    live_model = agent_app._live_model  # noqa: SLF001 — demo server reads AgentApp wiring
    registry = live_model.tool_registry()
    tool = registry.get(tool_name)
    if tool is None:
        raise KeyError(tool_name)

    result = await asyncio.to_thread(tool.execute, **body)
    if isinstance(result, str) and result.startswith("Error:"):
        return {"result": None, "error": result.removeprefix("Error:").strip()}

    await agent_app.event_bus.emit(
        StateUpdateEvent(
            state_data=live_model.state.model_dump(),
            display_schema=None,
        )
    )
    return {"result": result, "error": None}


def demo_app(agent_app: AgentApp) -> Any:
    """Create a FastAPI app configured for LiveModel demo mode.

    Thin alias around ``create_app`` so demo wiring stays in one import path.

    Args:
        agent_app: AgentApp with ``live_model`` set.

    Returns:
        Configured FastAPI application.
    """
    from agentflow.gui.server import create_app

    return create_app(agent_app)
