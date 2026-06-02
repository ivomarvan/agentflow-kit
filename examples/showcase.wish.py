"""agentflow showcase — Research & Evaluate pipeline demonstrating all framework features.

Two-vertex workflow: the agent first gathers facts (LLM + tools, loop hidden),
then evaluates whether the answer is sufficient. If not, it researches again.

Feature coverage:
  ▸ AgentApp            — declarative constructor, no subclassing for standard case
  ▸ StateGraph          — class-based transitions, initialized_vertexes for custom params
  ▸ StateVertex         — class-level Annotated[T, Field(...)] fields; no __init__ boilerplate
  ▸ Describable         — get_config_schema() auto-reads class-level Annotated fields
  ▸ achat_with_tools    — LLM+tool loop hidden inside connector; no ToolExecutionVertex
  ▸ Typed state in run  — state is typed directly; no cast() needed
  ▸ ctx.step / exceeded — framework step counter; no step field in AppState
  ▸ ctx.stats           — automatic token/timing stats; available in run() and after run
  ▸ ToolBase            — three tools with @param_desc JSON schema
  ▸ ToolRegistry        — keyed registries in Context
  ▸ LlmConnector        — keyed connectors in Context; different connectors per vertex
  ▸ LlmFileCache        — persistent per-script cache
  ▸ AgentEvent          — custom ToolCalledEvent (published inside achat_with_tools hook)

Run:
    uv run python examples/showcase.py -h           # help (full command grammar)
    uv run python examples/showcase.py run          # run with real LLM
    uv run python examples/showcase.py graph --browser
    uv run python examples/showcase.py gui          # start local GUI server
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import Field

from agentflow import AgentApp
from agentflow.events import AgentEvent
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.connectors import LlmConnector
from agentflow.statemachine import (
    Context,
    Signal,
    StateGraph,
    StateVertex,
    StdEnd,
    Transition,
)
from agentflow.tools.Tool import ToolBase, param_desc
from agentflow.tools.ToolRegistry import ToolRegistry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_QUESTION = (
    "What's the weather in Prague and Tokyo? Which city is warmer? "
    "Also, how much is 100 EUR in CZK?"
)
_SYSTEM_PROMPT = (
    "You are a helpful travel assistant. "
    "Use the available tools to obtain accurate facts. "
    "Never guess weather or currency data — always call a tool."
)

# ---------------------------------------------------------------------------
# Application state, patch and signals  (application-specific)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AppState:
    """Immutable state snapshot passed between vertices.

    Attributes:
        messages:     Conversation history (system + user + assistant turns).
        research:     Accumulated research notes from ResearchVertex.
        revision:     Number of completed evaluate→research loops.
        final_answer: Non-empty when EvaluateVertex has approved the answer.
    """

    messages:     Annotated[tuple[dict, ...], operator.add] = field(default_factory=tuple)
    research:     str = ""
    revision:     int = 0
    final_answer: str = ""


@dataclass(frozen=True)
class AppPatch:
    """Partial update emitted by each vertex; merged into AppState by the runner."""

    messages:     tuple[dict, ...] = field(default_factory=tuple)
    research:     str = ""
    revision:     int = 0
    final_answer: str = ""


class AppSignal(Signal):
    """Routing decisions emitted by vertices."""

    ready     = "ready"      # ResearchVertex done → EvaluateVertex
    satisfied = "satisfied"  # EvaluateVertex: answer is good → StdEnd
    revise    = "revise"     # EvaluateVertex: need more research → ResearchVertex


# ---------------------------------------------------------------------------
# Custom domain event  (optional — demonstrates EventBus usage)
# ---------------------------------------------------------------------------


class ToolCalledEvent(AgentEvent):
    """Emitted inside achat_with_tools for each tool invocation.

    Hook registered on LlmConnector (or on Context) at construction time.

    Attributes:
        tool_name: Name of the tool that was called.
        args:      Parsed argument dict.
        result:    Return value produced by the tool.
    """

    event_type: str = "showcase.tool_called"
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: str


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

_WEATHER_DB: dict[str, str] = {
    "Prague": "12°C, cloudy",
    "Tokyo": "24°C, sunny",
    "New York": "18°C, windy",
    "London": "9°C, rainy",
    "Paris": "15°C, partly cloudy",
    "Berlin": "7°C, overcast",
}

_RATES: dict[tuple[str, str], float] = {
    ("EUR", "CZK"): 25.2,
    ("USD", "CZK"): 23.1,
    ("GBP", "EUR"): 1.17,
    ("USD", "EUR"): 0.92,
}


class GetWeather(ToolBase):
    """Return current weather conditions for a city (stub data)."""

    name = "get_weather"
    description = "Return the current weather for the given city."

    @param_desc(city="City name, e.g. 'Prague' or 'Tokyo'.")
    def execute(self, city: str) -> str:
        return _WEATHER_DB.get(city, f"No weather data for '{city}'.")


class Calculator(ToolBase):
    """Evaluate a safe arithmetic expression and return the numeric result."""

    name = "calculator"
    description = "Evaluate a mathematical expression, e.g. '(17+8)*4'."

    @param_desc(expression="Arithmetic expression to evaluate, e.g. '42 * 7'.")
    def execute(self, expression: str) -> str:
        try:
            result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
            return str(result)
        except Exception as exc:
            return f"ERROR: {exc}"


class GetExchangeRate(ToolBase):
    """Return the current exchange rate between two currencies (stub data)."""

    name = "get_exchange_rate"
    description = "Return exchange rate between from_currency and to_currency."

    @param_desc(
        from_currency="Three-letter ISO code to convert FROM, e.g. 'EUR'.",
        to_currency="Three-letter ISO code to convert TO, e.g. 'CZK'.",
    )
    def execute(self, from_currency: str, to_currency: str) -> str:
        f, t = from_currency.upper(), to_currency.upper()
        rate = _RATES.get((f, t))
        if rate is None:
            inv = _RATES.get((t, f))
            rate = round(1.0 / inv, 6) if inv else None
        if rate is None:
            return f"No rate available for {f}/{t}."
        return f"1 {f} = {rate} {t}"


# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------


class ResearchVertex(StateVertex):
    """Gather facts by calling LLM with tools; tool-calling loop is hidden inside connector.

    The entire ReAct loop (LLM → tool calls → LLM …) runs inside achat_with_tools.
    This vertex only defines *what* to research and *where* to route the result.
    """

    # Class-level Annotated fields — no __init__, no self.x = x.
    # StateVertex (as BaseModel) auto-generates __init__ and exposes these in GUI Settings.
    connector:  Annotated[str, Field(description="LLM connector key from Context.")] = "default"
    tools:      Annotated[str, Field(description="Tool registry key from Context.")] = "default"
    max_rounds: Annotated[int, Field(ge=1, le=20, description="Max tool-calling rounds.")] = 5

    async def run(self, state: AppState, ctx: Context) -> tuple[AppSignal, AppPatch]:
        """Call LLM with tools; return gathered research notes.

        Args:
            state: Current AppState — messages and any prior research.
            ctx:   Shared services (connectors, registries, event bus, stats).

        Returns:
            (AppSignal.ready, patch) with research notes in patch.research.
        """
        prior = (
            [{"role": "assistant", "content": f"Prior research:\n{state.research}"}]
            if state.research else []
        )
        response = await ctx.llm(self.connector).achat_with_tools(
            messages=list(state.messages) + prior,
            registry=ctx.get_tools(self.tools),
            max_rounds=self.max_rounds,
        )
        return AppSignal.ready, AppPatch(research=response.text)


class EvaluateVertex(StateVertex):
    """Assess research quality; extract the final answer or request another research round."""

    connector:     Annotated[str, Field(description="LLM connector key from Context.")] = "quality"
    max_revisions: Annotated[int, Field(ge=1, le=5,
                       description="Max research→evaluate loops before forcing an answer.")] = 2

    async def run(self, state: AppState, ctx: Context) -> tuple[AppSignal, AppPatch]:
        """Evaluate research and decide: approve (satisfied) or request revision (revise).

        Args:
            state: Current AppState — messages and accumulated research.
            ctx:   Shared services.

        Returns:
            (AppSignal.satisfied, patch) with final_answer when research is sufficient.
            (AppSignal.revise, patch) to trigger another ResearchVertex run.
        """
        if state.revision >= self.max_revisions:
            ctx.logger.warning("max_revisions=%d reached; using research as final answer",
                               self.max_revisions)
            return AppSignal.satisfied, AppPatch(final_answer=state.research,
                                                  revision=state.revision + 1)

        response = await ctx.llm(self.connector).achat([
            *state.messages,
            {"role": "assistant", "content": state.research},
            {"role": "user", "content": (
                "Review the research above. "
                "If it fully answers the original question, start your reply with 'FINAL: '. "
                "Otherwise start with 'REVISE: ' and describe what is missing."
            )},
        ])
        text = response.text.strip()
        if text.upper().startswith("FINAL:"):
            return AppSignal.satisfied, AppPatch(
                final_answer=text[6:].strip(), revision=state.revision + 1
            )
        return AppSignal.revise, AppPatch(revision=state.revision + 1)


# ---------------------------------------------------------------------------
# Wiring — fully declarative AgentApp, no subclassing needed
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    _app = AgentApp(
        doc=__doc__,
        system_prompt=_SYSTEM_PROMPT,
        default_question=_DEFAULT_QUESTION,
        sample_prompts=[
            "What's the weather in Prague and Tokyo? Which city is warmer? Also 100 EUR in CZK?",
            "Is London or Paris warmer today? How much is 1 GBP in EUR?",
            "Compare weather in New York and Berlin.",
        ],
        initial_state_factory=lambda q: AppState(
            messages=(
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": q},
            ),
        ),
        context=Context(
            llm_connectors={
                "default": LlmConnector(model="gpt-4o-mini", cache=LlmFileCache(__file__)),
                "quality": LlmConnector(model="gpt-4o",      cache=LlmFileCache(__file__)),
            },
            tool_registries={
                "default": ToolRegistry([GetWeather(), Calculator(), GetExchangeRate()]),
            },
        ),
        state_graph=StateGraph(
            start=ResearchVertex,
            initialized_vertexes=[
                ResearchVertex(max_rounds=5),         # connector + tools use defaults
                EvaluateVertex(max_revisions=2),      # quality connector, 2 revision rounds
            ],
            transitions=[
                Transition(ResearchVertex,  AppSignal.ready,     EvaluateVertex),
                Transition(EvaluateVertex,  AppSignal.revise,    ResearchVertex),
                Transition(EvaluateVertex,  AppSignal.satisfied, StdEnd),
            ],
        ),
    )

    _app.cli(__doc__, name=__name__)


# ---------------------------------------------------------------------------
# Alternative: cli() instead of run_and_stats() for interactive use
#
#   AgentApp(...).cli(__doc__, name=__name__)
#   # handles -h, run, graph, gui subcommands from argv
# ---------------------------------------------------------------------------


# ===========================================================================
# Požadované změny v knihovně (requirements for implementation)
# ===========================================================================
#
# 1. StateVertex — Pydantic BaseModel  →  agentflow.statemachine.vertex
#
#    Rozhodnutí: StateVertex dědí přímo z Pydantic BaseModel.
#    Výhoda: __init__, validace, JSON Schema a round-trip zdarma; žádná vlastní magie.
#
#      class StateVertex(Describable, BaseModel):
#          model_config = ConfigDict(
#              frozen=False,                # run() může přiřazovat self.runtime_x
#              extra="allow",              # libovolné runtime atributy OK
#              arbitrary_types_allowed=True,
#          )
#
#    Uživatel definuje parametry jako class-level Annotated atributy:
#
#      class ResearchVertex(StateVertex):
#          connector:  Annotated[str, Field(description="...")] = "default"
#          max_rounds: Annotated[int, Field(ge=1, le=20, description="...")] = 5
#          # Žádný __init__, žádné self.x = x — Pydantic generuje automaticky.
#          # ResearchVertex(max_rounds=-1) → ValidationError: ge=1  ← zdarma
#          # ResearchVertex.model_json_schema() → JSON Schema pro GUI  ← zdarma
#
#    Metaclass: Python zvolí ModelMetaclass jako "most derived" automaticky,
#    pokud Describable nemá vlastní metaclass (používá type). Interní atributy
#    Describable musí být ClassVar[...] nebo _private, aby je Pydantic ignoroval.
#
# ---------------------------------------------------------------------------
#
# 2. Describable — get_config_schema() / get_param_values() / set_params()
#    →  agentflow.describable.describable
#
#    get_config_schema(self) -> dict[str, Any]
#      Pokud isinstance(self, BaseModel): vrátí type(self).model_json_schema()
#        s filtrem na scalar typy (int, float, str, bool, array) — komplexní
#        objektové parametry (context, state_graph, cache) jsou přeskočeny.
#      Fallback pro non-BaseModel třídy: create_model() z get_type_hints(__init__).
#
#    get_param_values(self) -> dict[str, Any]
#      Pokud BaseModel: self.model_dump() filtrovaný na scalar klíče.
#
#    set_params(self, **kwargs) -> None
#      Pokud BaseModel: validuje přes model_validate, pak setattr.
#      Fallback: setattr s kontrolou allowed keys.
#
# ---------------------------------------------------------------------------
#
# 3. Typovaný state v run()  →  agentflow.statemachine.runner
#
#    Runner čte type hint parametru state z run() signatury:
#      state_type = get_type_hints(vertex.run).get("state", object)
#    Před voláním run() provede:
#      typed_state = state_type(**asdict(current_raw_state))
#    Uživatel píše run(self, state: AppState, ...) bez cast().
#
# ---------------------------------------------------------------------------
#
# 4. ctx.step a ctx.exceeded(n)  →  agentflow.statemachine.context
#
#    ctx.step: int — aktuální číslo super-stepu (inkrementováno runnerem)
#    ctx.exceeded(n: int) -> bool — zkratka pro ctx.step >= n
#
#    Důsledek: step nemusí být polem AppState pokud ho nepoužívá vrchol pro
#    vlastní logiku. Revize a iterace si vrcholy stále mohou sledovat samy
#    přes patch (viz revision v AppState výše).
#
# ---------------------------------------------------------------------------
#
# 5. achat_with_tools  →  agentflow.llm.LlmConnectorBase
#
#    Nová metoda pro LLM + automatické volání nástrojů:
#
#      async def achat_with_tools(
#          self,
#          messages:   list[dict],
#          registry:   ToolRegistry,
#          max_rounds: int = 10,
#          temperature: float = 0.2,
#      ) -> ChatResponse:
#          """Execute LLM with automatic tool-calling loop.
#
#          Runs: LLM call → if tool_calls: execute all → append results → LLM call → ...
#          Repeats up to max_rounds. Returns final plain-text ChatResponse.
#          Emits ToolCalledEvent via ctx.event_bus for each tool call (if ctx available).
#          """
#
#    ToolExecutionVertex se tím stává nepovinný (zůstane v knihovně pro případy,
#    kdy chce uživatel vidět tool-calling jako vrcholy v grafu).
#
# ---------------------------------------------------------------------------
#
# 6. ctx.stats a RunStats  →  agentflow.statemachine.context
#
#    ctx.stats: RunStats — live objekt aktualizovaný LlmConnectorBase po každém volání:
#
#      @dataclass
#      class RunStats:
#          total_tokens:      int   = 0
#          prompt_tokens:     int   = 0
#          completion_tokens: int   = 0
#          wall_time_ms:      float = 0.0
#          llm_calls:         int   = 0
#          cache_hits:        int   = 0
#          by_vertex: dict[str, VertexStats] = field(default_factory=dict)
#
#    AgentApp.run_and_stats(question) -> tuple[str | None, RunStats]
#      Spustí run_workflow() a vrátí (výsledek, stats).
#    AgentApp.last_run_stats: RunStats — k dispozici po run_workflow().
#
# ---------------------------------------------------------------------------
#
# 7. Odstranění parametru name z Describable  →  agentflow.describable
#
#    name = type(self).__name__. Explicitní name= se odstraní ze všech konstruktorů.
#    Pro jiný display name uživatel subclassuje s jiným docstringem.
#
# ---------------------------------------------------------------------------
#
# 8. Context — slovníky connectorů a registrů  →  agentflow.statemachine.context
#
#    llm_connectors:  dict[str, LlmConnectorBase]   (musí obsahovat "default")
#    tool_registries: dict[str, ToolRegistry]        (musí obsahovat "default")
#
#    ctx.llm(key="default")   -> LlmConnectorBase  (fallback na "default" s WARNING)
#    ctx.tools(key="default") -> ToolRegistry       (fallback na "default" s WARNING)
#
# ---------------------------------------------------------------------------
#
# 9. AgentApp — declarative constructor  →  agentflow.app
#
#    Nové __init__ parametry: doc, system_prompt, default_question,
#    sample_prompts, context, state_graph.
#    Generický run_workflow(); přepisovatelné sub-metody:
#      build_runner_context(), set_init_state(q), extract_result(final_state).
#    run_and_stats(question) -> tuple[str | None, RunStats]
#
# ---------------------------------------------------------------------------
#
# 10. StateGraph — class-based transitions  →  agentflow.statemachine.topology
#
#    Transition + initialized_vertexes přijímají třídy i instance.
#    Nezadané třídy jsou auto-instantiated jako VertexClass() (výchozí hodnoty).
#
# ===========================================================================
