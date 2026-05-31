"""<Description>"""

# <Imports>

_DEFAULT_QUESTION = (
    "I haven't had vacation yet. If I take it all in three days from today, when will it end?"
)

_POLICIES: dict[str, str] = {
    "vacation": "Employees are entitled to 25 days of paid vacation per year.",
    "sick days": "Employees may take up to 3 sick days per year without a doctor's note.",
    "remote work": "Remote work is allowed up to 4 days a week.",
    "parking": "Parking at the HQ is free for all employees.",
}

_SYSTEM_PROMPT = (
    "You are a strict company assistant. "
    "To answer any question about policies, math, or dates you MUST always use the appropriate tool. "  # noqa: E501
    "Never assume facts — call search_policy for policy questions, calculator for arithmetic, "
    "get_current_date for today's date, and add_days_to_date for date arithmetic. "
    "Answer concisely in English."
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

# <Tools>


# ---------------------------------------------------------------------------
# State / Patch / Signal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReactState:
    """Immutable agent state for one ReAct run."""
    # <State definition - or default state definition exists>

@dataclass
class ReactPatch:
    """Mutable patch applied to ReactState after each super-step."""
    

class ReactSignal(EnumSignal):
    """Routing signals for the ReAct loop."""
    # <Signal definition - or default signal definition exists>


# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------

_MAX_STEPS = 10


class LlmCallVertex(StateVertex):
    """Calls the LLM and decides whether to invoke a tool or emit a final answer."""

    def __init__(self, tools: list[ToolBase], max_steps: int = 10) -> None:
        self._tool_schemas = [t.to_openai_schema() for t in tools]

    async def run(self, state: object, ctx: Context) -> tuple[ReactSignal, ReactPatch]:
        """Run one LLM turn and route based on the response type.

        Args:
            state: Current ReactState snapshot.
            ctx: Shared context with LLM connector.

        Returns:
            Tool-call patch when tools requested; final-answer patch otherwise.
        """
        s = cast(ReactState, state)
        if s.step >= _MAX_STEPS:
            return ReactSignal.max_steps, ReactPatch(
                final_answer=f"AGENT ERROR: exceeded {_MAX_STEPS} steps"
            )
        response = await ctx.connector.achat(list(s.messages), tools=self._tool_schemas)
        assistant_msg = response.to_message_dict()
        if response.has_tool_calls:
            return ReactSignal.tool_call, ReactPatch(
                messages=(assistant_msg,),
                last_tool_calls=tuple(response.tool_calls or []),
                step=s.step + 1,
            )
        return ReactSignal.final_answer, ReactPatch(
            messages=(assistant_msg,),
            final_answer=response.text,
            step=s.step + 1,
        )


class ToolExecutionVertex(StateVertex):
    """Executes all tool calls requested by the LLM in the previous step."""

    def __init__(self, tools: list[ToolBase]) -> None:
        self._tool_map: dict[str, ToolBase] = {t.name: t for t in tools}

    async def run(self, state: object, ctx: Context) -> tuple[Any, ReactPatch]:
        """Execute pending tool calls and return result messages.

        Args:
            state: Current ReactState snapshot.
            ctx: Shared context; logger used for structured output.

        Returns:
            (StdSignal.ok, patch) with tool result messages appended.
        """
        s = cast(ReactState, state)
        tool_msgs: list[dict[str, Any]] = []
        for tc in s.last_tool_calls:
            tool = self._tool_map.get(tc.name)
            ctx.logger.info("tool_call: name=%s", tc.name)
            if tool is None:
                result = f"ERROR: unknown tool '{tc.name}'"
            else:
                try:
                    args = json.loads(tc.arguments or "{}")
                    result = str(tool.execute(**args))
                except Exception as exc:  # noqa: BLE001
                    result = f"ERROR: {exc}"
            ctx.logger.info("tool_result: name=%s result=%.80s", tc.name, result)
            tool_msgs.append(
                {"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result}
            )
        return StdSignal.ok, ReactPatch(messages=tuple(tool_msgs), last_tool_calls=())


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class ReactAgentApp(AgentApp):
    """Full ReAct agent with policy search, calculator, and date tools."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = LlmConnector(cache=LlmFileCache(__file__))
        tools: list[ToolBase] = [SearchPolicy(), Calculator(), GetCurrentDate(), AddDaysToDate()]
        llm_vertex = LlmCallVertex(tools)
        tool_vertex = ToolExecutionVertex(tools)
        self.graph = StateGraph(
            start=llm_vertex,
            transitions=[
                Transition(llm_vertex, ReactSignal.tool_call, tool_vertex),
                Transition(tool_vertex, StdSignal.ok, llm_vertex),
                Transition(llm_vertex, ReactSignal.final_answer, StdEnd),
                Transition(llm_vertex, ReactSignal.max_steps, StdEnd),
            ],
        )

    @property
    def sample_prompts(self) -> list[str]:
        """Example prompts for the GUI prompt selector."""
        return [
            "What is twice the number of vacation days in our policy?",
            (
                "I haven't had vacation yet. "
                "If I take it all in three days from today, when will it end?"
            ),
            "How many remote work days am I allowed per week? And what date will it be in 14 days?",
        ]

    async def run_workflow(self) -> str | None:
        """Run the ReAct agent loop and print the final answer.

        Returns:
            Final answer string from the agent.
        """
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
        question = self.current_prompt or _DEFAULT_QUESTION
        ctx = Context(connector=self.connector, event_bus=self.event_bus)
        hooks = LoggingHooks()
        runner = StateGraphRunner(graph=self.graph, context=ctx, hooks=hooks)
        initial = ReactState(
            messages=(
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            )
        )
        final = cast(ReactState, await runner.run(initial))
        print(f"\nAnswer: {final.final_answer}")
        return final.final_answer


if __name__ == "__main__":
    app = App(

    )
    app().cli(__doc__, name=__name__)
