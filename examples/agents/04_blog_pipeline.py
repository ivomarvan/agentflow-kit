"""Sequential blog-writing pipeline: Researcher → Writer → Editor.

Demonstrates a linear multi-agent pipeline where each vertex plays a
distinct role (persona) and builds on the previous vertex's output:

  1. ResearcherVertex — collects 3 concise bullet points about the topic
  2. WriterVertex     — turns bullet points into a 150-word blog post
  3. EditorVertex     — polishes the draft for clarity and brevity

Each vertex issues one LLM call with a role-specific system prompt.

Run:
    uv run python examples/agents/04_blog_pipeline.py
    uv run python examples/agents/04_blog_pipeline.py gui
    uv run python examples/agents/04_blog_pipeline.py browser
"""

from dataclasses import dataclass
from typing import Any, cast

from agentflow import AgentApp
from agentflow.llm.cache import LlmFileCache
from agentflow.llm.connectors import LlmConnector
from agentflow.logging_config import setup_pretty_logging
from agentflow.statemachine import (
    Context,
    StateGraph,
    StateGraphRunner,
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


class ResearcherVertex(StateVertex):
    """Collects 3 concise bullet points about the topic via LLM."""

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
            {
                "role": "system",
                "content": (
                    "You are a Tech Researcher. Collect 3 concise bullet points about the topic."
                ),
            },
            {"role": "user", "content": state.topic},
        ]
        response = await ctx.llm("default").achat(messages)
        ctx.logger.info("researcher: notes_len=%d", len(response.text))
        return StdSignal.ok, BlogPatch(research_notes=response.text)


class WriterVertex(StateVertex):
    """Turns research bullet points into a 150-word blog post via LLM."""

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
            {
                "role": "system",
                "content": (
                    "You are a Tech Writer. Turn the bullet points into a 150-word blog post."
                ),
            },
            {"role": "user", "content": state.research_notes},
        ]
        response = await ctx.llm("default").achat(messages)
        ctx.logger.info("writer: draft_len=%d", len(response.text))
        return StdSignal.ok, BlogPatch(draft=response.text)


class EditorVertex(StateVertex):
    """Polishes the draft for clarity, grammar, and brevity via LLM."""

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
            {
                "role": "system",
                "content": (
                    "You are a ruthless Editor. "
                    "Polish the draft: improve clarity, fix grammar, keep it short."
                ),
            },
            {"role": "user", "content": state.draft},
        ]
        response = await ctx.llm("default").achat(messages)
        ctx.logger.info("editor: final_len=%d", len(response.text))
        return StdSignal.ok, BlogPatch(final_post=response.text)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class BlogPipelineApp(AgentApp):
    """Sequential blog pipeline: Researcher → Writer → Editor."""

    def __init__(self) -> None:
        super().__init__()
        self.connector = LlmConnector(cache=LlmFileCache(__file__))
        self.graph = StateGraph(
            start=ResearcherVertex,
            transitions=[
                Transition(ResearcherVertex, StdSignal.ok, WriterVertex),
                Transition(WriterVertex, StdSignal.ok, EditorVertex),
                Transition(EditorVertex, StdSignal.ok, StdEnd),
            ],
        )

    @property
    def sample_prompts(self) -> list[str]:
        """Example topics for the GUI prompt selector."""
        return [
            "BSP execution model in AI agents",
            "How large language models are changing software development",
            "The rise of autonomous coding agents in 2026",
        ]

    async def run_workflow(self) -> str | None:
        """Run the blog pipeline and print the final edited post.

        Returns:
            Final blog post string.
        """
        setup_pretty_logging()
        topic = self.current_prompt or _DEFAULT_TOPIC
        ctx = Context(
            llm_connectors={"default": self.connector},
            event_bus=self.event_bus,
        )
        hooks = LoggingHooks()
        runner = StateGraphRunner(graph=self.graph, context=ctx, hooks=hooks)
        final = cast(BlogState, await runner.run(BlogState(topic=topic)))
        print(f"\n=== FINAL BLOG POST ===\n{final.final_post}\n======================")
        return final.final_post


if __name__ == "__main__":
    BlogPipelineApp().cli(__doc__, name=__name__)
