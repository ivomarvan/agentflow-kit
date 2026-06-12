"""Sequential blog-writing pipeline: Researcher → Writer → Editor.

Demonstrates a linear multi-agent pipeline where each vertex plays a
distinct role (persona) and builds on the previous vertex's output:

  1. ResearcherVertex — collects 3 concise bullet points about the topic
  2. WriterVertex     — turns bullet points into a 150-word blog post
  3. EditorVertex     — polishes the draft for clarity and brevity

Each vertex issues one LLM call with a role-specific system prompt.
"""

# Run:
#     uv run python examples/agents/04_pipeline.py -h
#     uv run python examples/agents/04_pipeline.py run
#     uv run python examples/agents/04_pipeline.py gui
#     uv run python examples/agents/04_pipeline.py graph --browser

from dataclasses import dataclass
from typing import Annotated, Any, cast

from pydantic import Field

from agentflow import AgentApp
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.LlmPool import LlmPool
from agentflow.logging_config import setup_pretty_logging
from agentflow.statemachine import (
    Context,
    StateGraph,
    StateGraphRunner,
    LlmStateVertex,
    StateVertex,
    StdEnd,
    StdSignal,
    Transition,
)
from agentflow.statemachine.hooks import LoggingHooks

_DEFAULT_TOPIC = "BSP execution model in AI agents"


# ---------------------------------------------------------------------------
# State / Patch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlogState:
    """Immutable state for one blog-pipeline run."""

    topic: str = ""
    research_notes: str = ""
    draft: str = ""
    final_post: str = ""


@dataclass
class BlogPatch:
    """Mutable patch applied to BlogState after each super-step."""

    topic: str | None = None
    research_notes: str | None = None
    draft: str | None = None
    final_post: str | None = None


# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------
#
# system_prompt fields use json_schema_extra={"x-textarea": True}:
#   - Runtime value is still a plain str (one string for LLM system messages).
#   - Pydantic emits "x-textarea": true on that property in get_config_schema().
#   - The Inspector GUI TextareaRenderer matches that flag and shows a multi-line
#     textarea instead of a single-line input.
#   - Default text is one string; use triple quotes or explicit "\\n" in the
#     literal when you want visible line breaks in the editor.


class ResearcherVertex(LlmStateVertex):
    """Collects 3 concise bullet points about the topic via LLM."""

    model: Annotated[str, Field(
        description="LLM model name (e.g. 'gpt-4o-mini'). Empty = use pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "deepseek-v4-flash"

    # x-textarea: multi-line Inspector editor; value remains one str (see block above).
    system_prompt: Annotated[str, Field(
        description="Instruction for the researcher role when gathering topic facts.",
        json_schema_extra={"x-textarea": True},
    )] = "You are a Tech Researcher. Collect 3 concise bullet points about the topic."

    async def run(self, state: BlogState, ctx: Context) -> tuple[Any, BlogPatch]:
        """Call the LLM in a researcher role to gather key facts.

        Args:
            state: Current BlogState snapshot; topic is read from here.
            ctx: Shared context with LLM connector.

        Returns:
            (StdSignal.ok, patch) with research_notes populated.
        """
        ctx.logger.info("researcher: topic=%r", state.topic)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": state.topic},
        ]
        response = await ctx.llm_for_model(self.model).achat(
            messages, temperature=self.temperature
        )
        ctx.logger.info("researcher: notes_len=%d", len(response.text))
        return StdSignal.ok, BlogPatch(research_notes=response.text)


class WriterVertex(LlmStateVertex):
    """Turns research bullet points into a 150-word blog post via LLM."""

    model: Annotated[str, Field(
        description="LLM model name (e.g. 'gpt-4o-mini'). Empty = use pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "deepseek-v4-flash"

    # x-textarea: multi-line Inspector editor; value remains one str (see block above).
    system_prompt: Annotated[str, Field(
        description="Instruction for the writer role when drafting the blog post.",
        json_schema_extra={"x-textarea": True},
    )] = "You are a Tech Writer. Turn the bullet points into a 150-word blog post."

    async def run(self, state: BlogState, ctx: Context) -> tuple[Any, BlogPatch]:
        """Call the LLM in a writer role to draft the blog post.

        Args:
            state: Current BlogState snapshot; research_notes is read from here.
            ctx: Shared context with LLM connector.

        Returns:
            (StdSignal.ok, patch) with draft populated.
        """
        ctx.logger.info("writer: notes_len=%d", len(state.research_notes))
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": state.research_notes},
        ]
        response = await ctx.llm_for_model(self.model).achat(
            messages, temperature=self.temperature
        )
        ctx.logger.info("writer: draft_len=%d", len(response.text))
        return StdSignal.ok, BlogPatch(draft=response.text)


class EditorVertex(LlmStateVertex):
    """Polishes the draft for clarity, grammar, and brevity via LLM."""

    model: Annotated[str, Field(
        description="LLM model name (e.g. 'gpt-4o-mini'). Empty = use pool default.",
        json_schema_extra={"x-model-select": True},
    )] = "deepseek-v4-flash"

    # x-textarea: multi-line Inspector editor; value remains one str (see block above).
    system_prompt: Annotated[str, Field(
        description="Instruction for the editor role when polishing the draft.",
        json_schema_extra={"x-textarea": True},
    )] = (
        "You are a ruthless Editor. "
        "Polish the draft: improve clarity, fix grammar, keep it short."
    )

    async def run(self, state: BlogState, ctx: Context) -> tuple[Any, BlogPatch]:
        """Call the LLM in an editor role to refine the draft.

        Args:
            state: Current BlogState snapshot; draft is read from here.
            ctx: Shared context with LLM connector.

        Returns:
            (StdSignal.ok, patch) with final_post populated.
        """
        ctx.logger.info("editor: draft_len=%d", len(state.draft))
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": state.draft},
        ]
        response = await ctx.llm_for_model(self.model).achat(
            messages, temperature=self.temperature
        )
        ctx.logger.info("editor: final_len=%d", len(response.text))
        return StdSignal.ok, BlogPatch(final_post=response.text)


# ---------------------------------------------------------------------------
# Wiring — declarative AgentApp
# ---------------------------------------------------------------------------

_app = AgentApp(
    doc=__doc__,
    default_question=_DEFAULT_TOPIC,
    sample_prompts=[
        "BSP execution model in AI agents",
        "How large language models are changing software development",
        "The rise of autonomous coding agents in 2026",
    ],
    context=Context(pool=LlmPool(cache=LlmFileCache(__file__))),
    state_graph=StateGraph(
        start=ResearcherVertex,
        transitions=[
            Transition(ResearcherVertex, StdSignal.ok, WriterVertex),
            Transition(WriterVertex, StdSignal.ok, EditorVertex),
            Transition(EditorVertex, StdSignal.ok, StdEnd),
        ],
    ),
    initial_state_factory=lambda q: BlogState(topic=q or _DEFAULT_TOPIC),
)

_app._extract_result = lambda state: state.final_post  # type: ignore[method-assign, attr-defined]

if __name__ == "__main__":
    _app.cli(__doc__, name=__name__)
