"""LLM connector implementations — real backends and test fakes.

Available classes:
  - ``LlmConnector``           — smart connector; auto-selects backend from env
  - ``OpenAiConnector``        — OpenAI-compatible backends (openai, ollama, gemini, deepseek)
  - ``AnthropicConnector``     — Anthropic native API (claude-* models)
  - ``FakeLlmConnector``       — deterministic queue-based fake for tests
  - ``FakeLlmRegexConnector``  — regex-rule-based fake for richer test scenarios
"""

from agentflow.llm.connectors.AnthropicConnector import AnthropicConnector
from agentflow.llm.connectors.FakeLlmConnector import FakeLlmConnector
from agentflow.llm.connectors.FakeLlmRegexConnector import FakeLlmRegexConnector
from agentflow.llm.connectors.LlmConnector import LlmConnector
from agentflow.llm.connectors.OpenAiConnector import OpenAiConnector

__all__ = [
    "LlmConnector",
    "OpenAiConnector",
    "AnthropicConnector",
    "FakeLlmConnector",
    "FakeLlmRegexConnector",
]
