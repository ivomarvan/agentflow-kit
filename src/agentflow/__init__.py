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
from git_root_to_syspath import agr
agr()

from src.agentflow.llm.ChatResponse import ChatResponse, ToolCallFunction, ToolCallInfo, UsageInfo
from src.agentflow.llm.LlmConfig import LlmConfig, SUPPORTED_BACKENDS, OPENAI_COMPATIBLE_BACKENDS
from src.agentflow.llm.LlmConnector import LlmConnector
from src.agentflow.llm.connectors.OpenAiConnector import OpenAiConnector
from src.agentflow.llm.connectors.AnthropicConnector import AnthropicConnector
from src.agentflow.llm.OllamaManager import OllamaManager, OllamaModelInfo
from src.agentflow.tools.Tool import ToolBase, param_desc, build_parameters_schema
from src.agentflow.tools.ToolRegistry import ToolRegistry
from src.agentflow.agents.ToolAgent import ToolAgent
from src.agentflow.describable import Describable, Graph, Vertex, Edge, GraphRenderer

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
    # Self-description interface
    "Describable",
    "Graph",
    "Vertex",
    "Edge",
    "GraphRenderer",
]
