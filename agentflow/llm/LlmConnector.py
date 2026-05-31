"""Backward-compatible re-export of LlmConnector.

The concrete ``LlmConnector`` class has moved to
``agentflow.llm.connectors.LlmConnector``.  This module re-exports it so
that existing imports continue to work without modification::

    from agentflow.llm.LlmConnector import LlmConnector   # still works
    from agentflow.llm.LlmConnectorBase import LlmConnectorBase  # abstract base

To write a custom connector, inherit from ``LlmConnectorBase``::

    from agentflow.llm.LlmConnectorBase import LlmConnectorBase

    class MyConnector(LlmConnectorBase):
        @property
        def config(self) -> LlmConfig: ...
        def _do_chat(self, ...): ...
        async def _do_achat(self, ...): ...
"""

from agentflow.llm.connectors.LlmConnector import LlmConnector
from agentflow.llm.LlmConnectorBase import LlmConnectorBase

__all__ = ["LlmConnector", "LlmConnectorBase"]
