"""ToolAgent — an LLM agent with a fixed set of tools and a system prompt.

Encapsulates the complete ReAct-style (Reason → Act → Observe) agentic loop
in a single, self-contained object.  All case-specific configuration lives in
the constructor; no subclassing is required for typical use.

Typical usage::

    from src.agentflow import LlmConfig, LlmConnector, ToolAgent
    from src.agentflow.tools.common_tools.Calculator import Calculator
    from src.agentflow.tools.ToolRegistry import ToolRegistry

    agent = ToolAgent(
        connector=LlmConnector.create(LlmConfig.from_env()),
        tools=ToolRegistry(tools=[Calculator()]),
        system_prompt="You are a helpful math assistant. Use tools when needed.",
        name="math_demo",
    )

    answer = agent.run("What is 1234 * 5678?")

    # Self-documenting output (inherited from Describable):
    print(agent.get_description_markdown())   # Markdown with full structure
    print(agent.get_graph_dot())              # Graphviz DOT source
    agent.open_graph_browser()                # open diagram in browser

    # Unified CLI entry-point:
    agent.run_argparse(doc=__doc__, name=__name__,
                       default_question="What is 42 * 7?", default_command="run")

Design notes:
  - Accepts a ToolRegistry or a plain list of ToolBase instances (auto-wrapped).
  - Connector is injected (DI) — the agent owns no network resources itself.
  - Describable graph is built from public attributes: connector and tools.

Pattern: Strategy (the loop delegates tool dispatch to ToolRegistry).
"""

from __future__ import annotations

import logging
from typing import Any, Union

from git_root_to_syspath import agr
agr()

from src.agentflow.describable.describable import Describable
from src.agentflow.llm.LlmConnector import LlmConnector
from src.agentflow.tools.Tool import ToolBase
from src.agentflow.tools.ToolRegistry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolAgent(Describable):
    """LLM agent with a fixed tool set, system prompt, and ReAct loop.

    Args:
        connector: Active LlmConnector pointing to any supported backend.
        tools: ToolRegistry instance, or a plain list of ToolBase instances
               (automatically wrapped into a ToolRegistry).
        system_prompt: System-role instruction sent at the start of every turn.
        name: Short identifier (snake_case recommended).  Defaults to the
              class name when omitted.
        description: One-line human-readable purpose statement.  Defaults to
                     the class docstring when omitted.
        max_steps: Maximum number of LLM calls before the loop aborts.
        temperature: Sampling temperature passed to every LlmConnector.chat() call.
    """

    def __init__(
        self,
        connector: LlmConnector,
        tools: Union[ToolRegistry, list[ToolBase]],
        system_prompt: str,
        name: str = "",
        description: str = "",
        max_steps: int = 10,
        temperature: float = 0.2,
    ) -> None:
        super().__init__(name=name or None)
        if isinstance(tools, list):
            registry = ToolRegistry(tools=tools)
        else:
            registry = tools
        # Public attributes → appear in Describable graph and descriptions
        self.connector = connector
        self.tools = registry
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.temperature = temperature
        if description:
            self.description = description

    # ------------------------------------------------------------------
    # Agentic loop
    # ------------------------------------------------------------------

    def run(self, question: str) -> str:  # type: ignore[override]
        """Run the ReAct-style tool-calling loop for a single user question.

        The loop repeats:
          1. Send the current message history to the LLM (with tool schemas).
          2. If the response contains tool calls → execute each, append results.
          3. If the response is plain text → return it as the final answer.

        Args:
            question: User question or instruction.

        Returns:
            Final text answer from the LLM, or an error string when
            ``max_steps`` is exceeded.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]
        schemas = self.tools.schemas()

        for step in range(1, self.max_steps + 1):
            logger.debug("step=%d messages=%d", step, len(messages))
            response = self.connector.chat(
                messages, tools=schemas, temperature=self.temperature
            )
            messages.append(response.to_message_dict())

            if not response.has_tool_calls:
                logger.debug("step=%d final answer received", step)
                return response.text.strip()

            for tc in response.tool_calls:  # type: ignore[union-attr]
                logger.info("tool_call name=%s args=%s", tc.name, tc.arguments[:80])
                try:
                    result = self.tools.execute(tc.name, tc.arguments)
                except KeyError as exc:
                    result = f"ERROR: {exc}"
                logger.info("tool_result name=%s result=%s", tc.name, result[:80])
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                })

        logger.warning("max_steps=%d exceeded for agent=%s", self.max_steps, self.name)
        return "AGENT ERROR: exceeded max_steps"

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ToolAgent(name={self.name!r}, "
            f"tools={self.tools.names()}, "
            f"max_steps={self.max_steps})"
        )
