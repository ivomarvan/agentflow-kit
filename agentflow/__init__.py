"""Public API of the agentflow LLM agent orchestration library.

Quick start::

    from agentflow import LlmConnector, LlmConfig
    from agentflow.llm.cache import LlmFileCache

    connector = LlmConnector(cache=LlmFileCache(__file__))
    response = connector.chat([{"role": "user", "content": "Hello!"}])
    print(response.text)
"""

from agentflow.agents.ToolAgent import ToolAgent
from agentflow.app import AgentApp
from agentflow.config import ConfigParam
from agentflow.describable import Describable, Edge, Graph, GraphRenderer, Vertex
from agentflow.events import (
    AgentEvent,
    EventBus,
    LogEvent,
    LoggingEventHandler,
    RunCompleteEvent,
    RunErrorEvent,
    RunStatsEvent,
    StateUpdateEvent,
    StepEndEvent,
    StepStartEvent,
    ToolCallEvent,
)
from agentflow.gui.state_viewer import (
    IconHint,
    PanelHint,
    RoomHint,
    extract_display_schema,
    icon,
    panel,
    room,
)
from agentflow.llm.cache import LlmCacheBase, LlmFileCache, LlmMemoryCache
from agentflow.llm.ChatResponse import ChatResponse, ToolCallFunction, ToolCallInfo, UsageInfo
from agentflow.llm.connectors.AnthropicConnector import AnthropicConnector
from agentflow.llm.connectors.FakeLlmConnector import FakeLlmConnector
from agentflow.llm.connectors.FakeLlmRegexConnector import FakeLlmRegexConnector
from agentflow.llm.connectors.LlmConnector import LlmConnector
from agentflow.llm.connectors.OpenAiConnector import OpenAiConnector
from agentflow.llm.LlmConfig import OPENAI_COMPATIBLE_BACKENDS, SUPPORTED_BACKENDS, LlmConfig
from agentflow.llm.LlmConnectorBase import LlmConnectorBase
from agentflow.llm.LlmPool import LlmPool
from agentflow.llm.OllamaManager import OllamaManager, OllamaModelInfo
from agentflow.live_model import LiveModel, action
from agentflow.logging_config import PrettyFormatter, setup_pretty_logging
from agentflow.statemachine import (
    EnumSignal,
    LlmStateVertex,
    ReActPatch,
    ReActSignal,
    ReActState,
    Signal,
    StdSignal,
)
from agentflow.tools.Tool import ToolBase, build_parameters_schema, param_desc
from agentflow.tools.ToolRegistry import ToolRegistry

__all__ = [
    # Config
    "LlmConfig",
    "SUPPORTED_BACKENDS",
    "OPENAI_COMPATIBLE_BACKENDS",
    # Connector base & smart connector
    "LlmConnectorBase",
    "LlmConnector",
    # Pool — transparent connector management
    "LlmPool",
    # LiveModel
    "LiveModel",
    "action",
    # Backend-specific connectors
    "OpenAiConnector",
    "AnthropicConnector",
    # Fake connectors for testing
    "FakeLlmConnector",
    "FakeLlmRegexConnector",
    # Cache
    "LlmCacheBase",
    "LlmFileCache",
    "LlmMemoryCache",
    # Ollama management
    "OllamaManager",
    "OllamaModelInfo",
    # Response types
    "ChatResponse",
    "ToolCallInfo",
    "ToolCallFunction",
    "UsageInfo",
    # Tool layer
    "ToolBase",
    "ToolRegistry",
    "param_desc",
    "build_parameters_schema",
    # Agents
    "ToolAgent",
    # Application base class
    "AgentApp",
    "ExampleApp",  # deprecated alias — use AgentApp
    # Logging utilities
    "setup_pretty_logging",
    "PrettyFormatter",
    # Configuration introspection
    "ConfigParam",
    # Domain events
    "AgentEvent",
    "EventBus",
    "LoggingEventHandler",
    "StepStartEvent",
    "StepEndEvent",
    "ToolCallEvent",
    "RunStatsEvent",
    "StateUpdateEvent",
    "LogEvent",
    "RunCompleteEvent",
    "RunErrorEvent",
    # Self-description interface
    "Describable",
    "Graph",
    "Vertex",
    "Edge",
    "GraphRenderer",
    # State machine
    "EnumSignal",
    "LlmStateVertex",
    "StdSignal",
    "Signal",
    "ReActState",
    "ReActPatch",
    "ReActSignal",
    # State viewer DSL
    "icon",
    "room",
    "panel",
    "IconHint",
    "RoomHint",
    "PanelHint",
    "extract_display_schema",
]

# Backward-compatible alias — use AgentApp in new code
ExampleApp = AgentApp
