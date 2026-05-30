"""Chapter 06 demo: a minimal 3-agent team with CrewAI.

Roles:
  * Researcher - collects key points about a topic.
  * Writer     - turns the points into a blog post draft.
  * Editor     - polishes the draft.

By default this uses a local Ollama model via the OpenAI-compatible API.
To run against OpenAI instead, set OPENAI_API_KEY and remove the env overrides.

Run:
    pip install -r requirements.txt
    ollama pull qwen2.5:7b-instruct
    python 06_crewai_blog_team.py
"""

from __future__ import annotations

import os

# Point CrewAI's underlying LLM calls to the local Ollama server.
# CrewAI uses LiteLLM which understands the OPENAI_* env vars.
os.environ.setdefault("OPENAI_API_BASE", "http://localhost:11434/v1")
os.environ.setdefault("OPENAI_API_KEY", "ollama-local")
os.environ.setdefault("OPENAI_MODEL_NAME", "qwen2.5:7b-instruct")

from crewai import Agent, Crew, Task  # noqa: E402


LLM_MODEL = f"ollama/{os.environ['OPENAI_MODEL_NAME']}"


def build_crew(topic: str) -> Crew:
    researcher = Agent(
        role="Tech Researcher",
        goal=f"Collect 3 concise, factual bullet points about: {topic}",
        backstory="You are meticulous and prefer sources you can cite.",
        llm=LLM_MODEL,
        verbose=True,
        allow_delegation=False,
    )

    writer = Agent(
        role="Tech Writer",
        goal="Turn bullet points into an engaging 150-word blog post.",
        backstory="You write crisply for embedded-systems developers.",
        llm=LLM_MODEL,
        verbose=True,
        allow_delegation=False,
    )

    editor = Agent(
        role="Editor",
        goal="Polish the draft - improve clarity, fix grammar, keep it short.",
        backstory="You are a ruthless editor who cuts fluff.",
        llm=LLM_MODEL,
        verbose=True,
        allow_delegation=False,
    )

    research_task = Task(
        description=f"Find the 3 most important recent facts about: {topic}.",
        expected_output="A 3-bullet list, each under 25 words.",
        agent=researcher,
    )

    writing_task = Task(
        description="Using the research bullets, write a ~150-word blog post.",
        expected_output="Markdown-formatted blog post, 150 words.",
        agent=writer,
        context=[research_task],
    )

    editing_task = Task(
        description="Polish the blog post - tighten prose, fix grammar.",
        expected_output="Final Markdown blog post ready to publish.",
        agent=editor,
        context=[writing_task],
    )

    return Crew(
        agents=[researcher, writer, editor],
        tasks=[research_task, writing_task, editing_task],
        verbose=True,
    )


if __name__ == "__main__":
    topic = "ESP32-S3 and AI at the edge"
    crew = build_crew(topic)
    result = crew.kickoff()

    print("\n========== FINAL ARTICLE ==========")
    print(result)
