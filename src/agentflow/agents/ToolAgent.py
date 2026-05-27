"""ToolAgent — an LLM agent with a fixed set of tools and a system prompt.

Encapsulates the complete ReAct-style (Reason → Act → Observe) agentic loop
in a single, self-contained object.  All case-specific configuration lives in
the constructor; no subclassing is required for typical use.

Typical usage::

    from src.agentflow import LlmConfig, LlmConnector, ToolAgent
    from src.agentflow.tools.common_tools.Calculator import Calculator

    agent = ToolAgent(
        connector=LlmConnector.create(LlmConfig.from_env()),
        tools=[Calculator()],
        system_prompt="You are a helpful math assistant. Use tools when needed.",
        name="math_demo",
        description="Demonstrates calculator tool-calling.",
    )

    answer = agent.run("What is 1234 * 5678?")

    # Self-documenting output:
    print(agent.get_markdown())          # Markdown
    print(agent.get_json())              # dict (JSON-serializable)
    print(agent.get_dot())               # Graphviz DOT source
    agent.open_browser()                 # open diagram in browser

Design notes:
  - Accepts a list of ToolBase instances; builds ToolRegistry internally.
  - Connector is injected (DI) — the agent owns no network resources itself.
  - Describable methods do not call the LLM; they are pure, cheap operations.
  - get_graphviz_fragment() composes the diagram from connector + tools
    by calling their own get_graphviz_fragment() implementations.

Pattern: Strategy (the loop delegates tool dispatch to ToolRegistry).
"""

from __future__ import annotations

import logging
import textwrap
from typing import Any

from git_root_to_syspath import agr
agr()

from src.agentflow.describe import Describable, GraphContext, GraphFragment, _esc
from src.agentflow.llm.LlmConnector import LlmConnector
from src.agentflow.tools.Tool import ToolBase
from src.agentflow.tools.ToolRegistry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolAgent(Describable):
    """LLM agent with a fixed tool set, system prompt, and ReAct loop.

    Args:
        connector: Active LlmConnector pointing to any supported backend.
        tools: List of ToolBase instances available to the LLM.
        system_prompt: System-role instruction sent at the start of every turn.
        name: Short identifier (snake_case recommended).
        description: One-line human-readable purpose statement.
        max_steps: Maximum number of LLM calls before the loop aborts.
        temperature: Sampling temperature passed to every LlmConnector.chat() call.
    """

    def __init__(
        self,
        connector: LlmConnector,
        tools: list[ToolBase],
        system_prompt: str,
        name: str = "",
        description: str = "",
        max_steps: int = 10,
        temperature: float = 0.2,
    ) -> None:
        self._connector = connector
        self._tools = list(tools)
        self._registry = ToolRegistry()
        for tool in self._tools:
            self._registry.register(tool)
        self._system_prompt = system_prompt
        self.name = name or "unnamed_agent"
        self.description = description
        self.max_steps = max_steps
        self.temperature = temperature

    # ------------------------------------------------------------------
    # Agentic loop
    # ------------------------------------------------------------------

    def run(self, question: str) -> str:
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
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": question},
        ]
        schemas = self._registry.schemas()

        for step in range(1, self.max_steps + 1):
            logger.debug("step=%d messages=%d", step, len(messages))
            response = self._connector.chat(
                messages, tools=schemas, temperature=self.temperature
            )
            messages.append(response.to_message_dict())

            if not response.has_tool_calls:
                logger.debug("step=%d final answer received", step)
                return response.text.strip()

            for tc in response.tool_calls:  # type: ignore[union-attr]
                logger.info("tool_call name=%s args=%s", tc.name, tc.arguments[:80])
                try:
                    result = self._registry.execute(tc.name, tc.arguments)
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
    # Describable — compositional implementations
    # Each method asks the connector and tools for their own descriptions
    # and assembles the results into the agent-level document/diagram.
    # ------------------------------------------------------------------

    def get_markdown(self) -> str:
        """Return a Markdown document describing this agent's full configuration.

        Composes descriptions from the connector and each tool by calling
        their ``get_markdown()`` implementations.

        Returns:
            Markdown-formatted string suitable for printing or saving to a file.
        """
        cfg = self._connector.config
        lines: list[str] = [f"# Agent: `{self.name}`"]
        if self.description:
            lines += ["", self.description]

        lines += [
            "",
            "## Configuration",
            "",
            "| Property | Value |",
            "|----------|-------|",
            f"| Backend | `{cfg.backend}` |",
            f"| Model | `{cfg.model}` |",
            f"| Max steps | {self.max_steps} |",
            f"| Temperature | {self.temperature} |",
            f"| Tools | {len(self._tools)} |",
        ]

        prompt = textwrap.dedent(self._system_prompt).strip()
        lines += ["", "## System prompt", "", "```", prompt, "```"]

        # Delegate to connector
        lines += ["", self._connector.get_markdown()]

        # Delegate to each tool
        lines.append(f"\n## Tools ({len(self._tools)})")
        for tool in self._tools:
            lines += ["", tool.get_markdown()]

        return "\n".join(lines)

    def get_json(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of the agent's full configuration.

        Composes sub-dicts from the connector and each tool by calling their
        ``get_json()`` implementations.

        Returns:
            Dict with ``name``, ``description``, ``connector``, ``max_steps``,
            ``temperature``, ``system_prompt``, and ``tools`` keys.
        """
        return {
            "name": self.name,
            "description": self.description,
            "connector": self._connector.get_json(),
            "max_steps": self.max_steps,
            "temperature": self.temperature,
            "system_prompt": self._system_prompt,
            "tools": [tool.get_json() for tool in self._tools],
        }

    def _build_tooltip_md(self) -> str:
        """Return a Markdown description of this agent's own scalar parameters.

        Used as the Cytoscape tooltip for the ToolAgent node.  Does NOT
        include nested connector or tool descriptions — those have their
        own nodes and tooltips.

        Returns:
            Markdown string with name, description, and constructor params.
        """
        prompt = textwrap.dedent(self._system_prompt).strip()
        return (
            f"# ToolAgent: `{self.name}`\n\n"
            f"{self.description}\n\n"
            f"## Parameters\n\n"
            f"| Parameter | Value |\n|---|---|\n"
            f"| `name` | `{self.name}` |\n"
            f"| `max_steps` | {self.max_steps} |\n"
            f"| `temperature` | {self.temperature} |\n\n"
            f"## System prompt\n\n"
            f"```\n{prompt}\n```\n"
        )

    def get_graphviz_fragment(self, ctx: GraphContext) -> GraphFragment:
        """Return a DOT cluster subgraph for this agent.

        Calls ``get_graphviz_fragment()`` on the connector and on each tool,
        collects their nodes, then wraps everything in a labeled
        ``subgraph cluster_*`` block.

        For Cytoscape.js HTML output: creates an *agent* compound node, a
        *registry* compound node for tools inside the agent, and uses
        ``ctx.set_parent()`` to nest the connector and each tool inside their
        respective containers.

        Args:
            ctx: Mutable context for unique node-ID allocation and Cytoscape data.

        Returns:
            ``GraphFragment`` with one subgraph statement and the agent's
            central node ID as ``root_id``.
        """
        agent_id = ctx.alloc_id(f"agent_{self.name}")
        cluster_id = f"cluster_{ctx.alloc_id(self.name)}"

        body: list[str] = []

        # The cluster subgraph IS the visual ToolAgent shape — no separate
        # central node needed.  We still register agent_id in descriptions so
        # the SVG tooltip can fire when hovering the cluster label area.
        ctx.add_node(agent_id, "ToolAgent", description_md=self._build_tooltip_md(),
                     node_class="agent")

        # ---- Connector (delegated; connector registers its own cy node) -----
        conn_frag = self._connector.get_graphviz_fragment(ctx)
        body.extend(conn_frag.dot_statements)
        # Cytoscape: nest connector inside the agent container
        ctx.set_parent(conn_frag.root_id, agent_id)

        # ---- Tools container ------------------------------------------------
        tools_tooltip_md = (
            f"## Tools ({len(self._tools)})\n\n"
            + "\n".join(f"- `{t.name}` ({type(t).__name__})" for t in self._tools)
        )
        # Cytoscape: compound container node nested inside the agent
        tools_cy_id = ctx.alloc_id(f"tools_{self.name}")
        ctx.add_node(tools_cy_id, "Tools", description_md=tools_tooltip_md,
                     node_class="registry", parent_id=agent_id)

        # DOT: a cluster subgraph gives visual containment in static / SVG output
        tools_cluster_id = f"cluster_tools_{self.name}"
        ctx.descriptions[tools_cluster_id] = tools_tooltip_md

        tools_dot_body: list[str] = []
        for tool in self._tools:
            tool_frag = tool.get_graphviz_fragment(ctx)
            tools_dot_body.extend(tool_frag.dot_statements)
            # Cytoscape: nest each tool inside the Tools container
            ctx.set_parent(tool_frag.root_id, tools_cy_id)

        inner_tools = "\n      ".join(tools_dot_body)
        body.append(
            f"subgraph {tools_cluster_id} {{\n"
            f'      label="Tools"\n'
            f"      style=\"rounded,filled,dashed\"\n"
            f"      fillcolor=lavender\n"
            f"      color=purple\n"
            f"      {inner_tools}\n"
            f"    }}"
        )

        # ---- Wrap in DOT cluster subgraph -----------------------------------
        # Register cluster IDs so SVG tooltips can match graphviz <title> elements
        ctx.descriptions[cluster_id] = self._build_tooltip_md()

        inner = "\n    ".join(body)
        cluster = (
            f"subgraph {cluster_id} {{\n"
            f'    label="ToolAgent"\n'
            f"    labeljust=l\n"
            f'    style="rounded,filled"\n'
            f"    fillcolor=lemonchiffon\n"
            f"    color=goldenrod\n"
            f"    {inner}\n"
            f"  }}"
        )

        return GraphFragment(dot_statements=[cluster], root_id=agent_id)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ToolAgent(name={self.name!r}, "
            f"tools={self._registry.names()}, "
            f"max_steps={self.max_steps})"
        )
