"""Structure example — structural skeletons mirroring 02_tool_calling_demo.py.

All classes here are intentionally stripped of any agent or LLM functionality.
They exist only to represent the **composition structure** so that the
Describable machinery can render it correctly.

The composition mirrors the real demo::

    ToolAgent
      ├── LlmConnector
      │     └── LlmConfig
      └── ToolRegistry
            ├── Calculator
            └── FakeWeather

Run directly to explore all output formats::

    python src/describe/structure_example.py            # default: run()
    python src/describe/structure_example.py dict       # JSON dict
    python src/describe/structure_example.py markdown   # Markdown
    python src/describe/structure_example.py html -o /tmp/out.html
"""

from __future__ import annotations

from typing import Any

from git_root_to_syspath import agr
agr()

from src.agentflow.tools.Tool import build_parameters_schema, param_desc
from src.describe.describable import Describable


# ---------------------------------------------------------------------------
# LLM layer
# ---------------------------------------------------------------------------


class LlmConfig(Describable):
    """LLM backend configuration: which provider and which model to use."""

    def __init__(self, backend: str, model: str) -> None:
        super().__init__()
        self.backend = backend
        self.model = model


class LlmConnector(Describable):
    """Connection to an LLM provider, configured via LlmConfig."""

    def __init__(self, config: LlmConfig) -> None:
        super().__init__()
        self.config = config


# ---------------------------------------------------------------------------
# Tool layer
# ---------------------------------------------------------------------------


class ToolBase(Describable):
    """Structural stub for an LLM tool — no execution logic."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name=name)

    def execute(self, **kwargs: Any) -> Any:
        """Override in subclasses with concrete tool parameters and logic."""
        ...

    def _get_own_attributes(self) -> dict[str, Any]:
        """Extend the base attributes with the execute() parameter schema.

        Uses the ``@param_desc`` annotations on the concrete subclass's
        ``execute()`` to populate the ``"parameters"`` key.

        Returns:
            Base attributes extended with a ``"parameters"`` entry.
        """
        d = super()._get_own_attributes()
        d["parameters"] = build_parameters_schema(type(self).execute)
        return d


class Calculator(ToolBase):
    """Evaluate a safe arithmetic expression and return the numeric result."""

    def __init__(self) -> None:
        super().__init__(name="calculator")

    @param_desc(expression="Arithmetic expression to evaluate, e.g. '19 * 23' or '(4 + 5) / 3'.")
    def execute(self, expression: str) -> str:  # type: ignore[override]
        """Evaluate the expression and return its result as a string.

        Args:
            expression: Arithmetic expression using digits and +-*/() only.

        Returns:
            Numeric result as a string, or an error message prefixed with ``ERROR:``.
        """
        ...


class FakeWeather(ToolBase):
    """Return the current weather for a given city (hard-coded demo stub)."""

    def __init__(self) -> None:
        super().__init__(name="fake_weather")

    @param_desc(city="City name, e.g. 'Prague'.")
    def execute(self, city: str) -> str:  # type: ignore[override]
        """Look up weather for the city from a hard-coded database.

        Args:
            city: City name.

        Returns:
            Weather description string, or ``"Unknown city"`` when not found.
        """
        ...


class ToolRegistry(Describable):
    """Registry holding all tools available to the agent."""

    def __init__(self, tools: list[ToolBase]) -> None:
        super().__init__()
        self.tools = tools


# ---------------------------------------------------------------------------
# Agent layer
# ---------------------------------------------------------------------------


class ToolAgent(Describable):
    """Orchestrates an LLM connector with a registry of tools — structural skeleton only."""

    def __init__(
        self,
        connector: LlmConnector,
        tools: ToolRegistry,
        system_prompt: str,
        name: str | None = None,
        max_steps: int = 10,
        temperature: float = 0.2,
    ) -> None:
        super().__init__(name=name)
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.temperature = temperature
        self.connector = connector
        self.tools = tools

    def run(self) -> str | None:
        """Placeholder — override with the actual ReAct loop in production.

        Returns:
            Informational string confirming that run() was called.
        """
        return (
            f"[{self.name}] run() called — "
            "override with the real agentic loop in production."
        )


# ---------------------------------------------------------------------------
# Demo composition — mirrors 02_tool_calling_demo.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    agent = ToolAgent(
        name="tool_calling_demo",
        connector=LlmConnector(
            config=LlmConfig(backend="ollama", model="qwen3:4b"),
        ),
        tools=ToolRegistry(tools=[Calculator(), FakeWeather()]),
        system_prompt=(
            "You are a helpful assistant. "
            "When a tool would give a more reliable answer, call it. "
            "Otherwise answer directly. "
            "Be concise."
        ),
        max_steps=6,
    )

    agent.run_argparse(default_command="run")
