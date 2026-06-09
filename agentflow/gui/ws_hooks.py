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
        """Broadcast *event* to all WebSocket clients for this run and buffer it.

        Builds a JSON payload with ``type`` set to the last dot-separated
        segment of ``event.event_type`` (e.g. ``"step_start"``).
        Uses ``mode='json'`` on ``model_dump`` so that ``datetime`` fields are
        serialised to ISO strings rather than left as raw Python objects (which
        are not JSON-serialisable by ``json.dumps``).

        The payload is also appended to ``run_state.run_events[run_id]`` so that
        WebSocket clients connecting after the event fires (race condition for
        fast synchronous workflows) can receive a full replay on connect.

        Args:
            event: The domain event to forward.
        """
        payload: dict[str, object] = {
            "type": event.event_type.split(".")[-1],
            "run_id": self._run_id,
            **event.model_dump(exclude={"run_id"}, mode="json"),
        }

        # Buffer every payload for late-joining WebSocket clients.
        events_buf = self._run_state.run_events.setdefault(self._run_id, [])
        events_buf.append(payload)

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
