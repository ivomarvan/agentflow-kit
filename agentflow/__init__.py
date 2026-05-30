"""Public API of the ``src.agentflow`` LLM abstraction library.

Quick start::

    from src.agentflow import LlmConfig, LlmConnector

    connector = LlmConnector.create(LlmConfig.from_env())
    print(connector.describe())

    response = connector.chat([{"role": "user", "content": "Hello!"}])
    print(response.text)
"""

# Ensure the repository root is in sys.path so that ``src.*`` imports work
# when the library (or its tests) is loaded from any working directory.

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
    StepEndEvent,
    StepStartEvent,
)
from agentflow.llm.ChatResponse import ChatResponse, ToolCallFunction, ToolCallInfo, UsageInfo
from agentflow.llm.connectors.AnthropicConnector import AnthropicConnector
from agentflow.llm.connectors.OpenAiConnector import OpenAiConnector
from agentflow.llm.LlmConfig import OPENAI_COMPATIBLE_BACKENDS, SUPPORTED_BACKENDS, LlmConfig
from agentflow.llm.LlmConnector import LlmConnector
from agentflow.llm.OllamaManager import OllamaManager, OllamaModelInfo
from agentflow.statemachine import EnumSignal, StdSignal
from agentflow.tools.Tool import ToolBase, build_parameters_schema, param_desc
from agentflow.tools.ToolRegistry import ToolRegistry

__all__ = [
    # Config & connectors
    "LlmConfig",
    "LlmConnector",
    "OpenAiConnector",
    "AnthropicConnector",
    "SUPPORTED_BACKENDS",
    "OPENAI_COMPATIBLE_BACKENDS",
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
    # Configuration introspection
    "ConfigParam",
    # Domain events
    "AgentEvent",
    "EventBus",
    "LoggingEventHandler",
    "StepStartEvent",
    "StepEndEvent",
    "LogEvent",
    "RunCompleteEvent",
    "RunErrorEvent",
    # Self-description interface
    "Describable",
    "Graph",
    "Vertex",
    "Edge",
    "GraphRenderer",
    # State machine (Epic E010)
    "EnumSignal",
    "StdSignal",
]

# Backward-compatible alias — use AgentApp in new code
ExampleApp = AgentApp
