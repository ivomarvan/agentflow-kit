"""Chapter 02 — tool-calling demo rewritten with src.agentflow.

Demonstrates the same flow as orig/02_tool_calling_demo.py, but using the
project's own library instead of the standalone llm_client.py helper:

  - LlmConfig / LlmConnector        instead of chat() / BACKEND / MODEL
  - ToolBase subclasses              instead of plain functions + hand-written JSON
  - ToolRegistry (inside ToolAgent)  instead of TOOLS_IMPL dict + TOOLS_SCHEMA list
  - ToolAgent                        encapsulates the entire agentic loop

Tools used:
  - Calculator   (src.agentflow.tools.common_tools) — reusable, general-purpose
  - FakeWeather  (defined here)               — demo stub, not worth generalising

Use  python .../my/02_tool_calling_demo.py -h  for full command list.

Switch backend:
    LLM_BACKEND=openai python .../my/02_tool_calling_demo.py
    LLM_BACKEND=gemini python .../my/02_tool_calling_demo.py
    LLM_MODEL=qwen3:8b python .../my/02_tool_calling_demo.py
"""

from __future__ import annotations

import logging
import os
from datetime import date as _date

from git_root_to_syspath import agr
agr()

from src.agentflow.agents.ToolAgent import ToolAgent
from src.agentflow.llm.LlmConfig import LlmConfig
from src.agentflow.llm.LlmConnector import LlmConnector
from src.agentflow.tools.Tool import ToolBase, param_desc
from src.agentflow.tools.ToolRegistry import ToolRegistry
from src.agentflow.tools.common_tools.Calculator import Calculator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Demo-specific tool (not general enough for src/lib/tools/common_tools/)
# ---------------------------------------------------------------------------

class FakeWeather(ToolBase):
    """Return the current weather for a given city.

    This is a demo stub returning hard-coded data.
    A real implementation would call a weather API here.
    """

    _WEATHER_DB: dict[str, str] = {
        "Prague": "12 C, cloudy",
        "Tokyo": "24 C, sunny",
        "New York": "18 C, windy",
    }

    @param_desc(city="City name, e.g. 'Prague'.")
    def execute(self, city: str) -> str:
        """Look up weather for the city from the hard-coded database.

        Args:
            city: City name.

        Returns:
            Weather description string, or ``"Unknown city"`` when not found.
        """
        result = self._WEATHER_DB.get(city, "Unknown city")
        logger.debug("FakeWeather: city=%s result=%s", city, result)
        return result


# ---------------------------------------------------------------------------
# Entry point — the entire __main__ section is now 10 lines
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    case = ToolAgent(
        connector=LlmConnector.create(LlmConfig.from_env()),
        tools=ToolRegistry(tools=[Calculator(), FakeWeather()]),
        system_prompt=(
            "You are a helpful assistant. "
            "When a tool would give a more reliable answer, call it. "
            "Otherwise answer directly. "
            "Be concise."
        ),
        name="tool_calling_demo",
        description=(
            "Demonstrates LLM tool-calling: arithmetic via Calculator "
            "and city weather via FakeWeather stub."
        ),
        max_steps=6,
    )

    _title = os.path.basename(__file__)
    _title_tooltip = (
        f"**{_title}**\n\n"
        f"_{_date.today()}_\n\n"
        f"{__doc__}"
    )
    case.run_argparse(
        doc=__doc__,
        name=__name__,
        title=_title,
        title_tooltip=_title_tooltip,
        default_question=(
            "What's the weather in Prague? "
            "And what is the Prague temperature (the number only) multiplied by 23?"
        ),
        default_command="run",
    )
