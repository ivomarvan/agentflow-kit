"""WebSocket event handler — forwards AgentEvents to connected WS clients.

The handler is registered on an EventBus at the start of a workflow run
and unregistered when the run completes or fails.

Pattern: Observer (GoF) — WebSocketEventHandler subscribes to the EventBus
and broadcasts each event as a JSON message to all WebSocket clients that
joined the matching ``run_id`` channel.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agentflow.events import AgentEvent

if TYPE_CHECKING:
    from agentflow.gui.server import RunState

logger = logging.getLogger(__name__)


class WebSocketEventHandler:
    """Forwards AgentEvents to connected WebSocket clients as JSON messages.

    One instance is created per workflow run and subscribed to the shared
    EventBus.  It looks up the list of active WebSocket connections for
    ``run_id`` on every event and broadcasts the payload to each client.
    Dead connections (send raises) are removed from the list silently.

    Args:
        run_id: Unique identifier of the workflow run.
        run_state: Shared ``RunState`` held on ``FastAPI.state``.
    """

    def __init__(self, run_id: str, run_state: RunState) -> None:
        self._run_id = run_id
        self._run_state = run_state

    async def on_event(self, event: AgentEvent) -> None:
        """Broadcast *event* to all WebSocket clients for this run.

        Builds a JSON payload with ``type`` set to the last dot-separated
        segment of ``event.event_type`` (e.g. ``"step_start"``).

        Args:
            event: The domain event to forward.
        """
        payload: dict[str, object] = {
            "type": event.event_type.split(".")[-1],
            "run_id": self._run_id,
            **event.model_dump(exclude={"run_id"}),
        }
        clients = self._run_state.ws_clients.get(self._run_id, [])
        dead = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                logger.debug("WebSocket send failed for run_id=%s — marking dead", self._run_id)
                dead.append(ws)
        for ws in dead:
            clients.remove(ws)
