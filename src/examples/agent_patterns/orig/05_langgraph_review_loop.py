"""Chapter 05 demo: LangGraph with a retrieve -> generate -> review cycle.

The graph loops back from `review` to `generate` until either:
  * the draft is approved, OR
  * we exceed MAX_ATTEMPTS.

No real LLM here - the nodes are pure Python so the graph logic itself
is the star. Swap the stubs for real LLM calls once you're comfortable.

Run:
    pip install -r requirements.txt
    python 05_langgraph_review_loop.py
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph


MAX_ATTEMPTS = 3


# -----------------------------------------------------------------------------
# State definition
# -----------------------------------------------------------------------------
class ReviewState(TypedDict, total=False):
    question: str
    context: list[str]
    draft: str
    approved: bool
    attempts: int
    feedback: str


# -----------------------------------------------------------------------------
# Nodes
# -----------------------------------------------------------------------------
def retrieve(state: ReviewState) -> ReviewState:
    """Simulated RAG. In reality this would query Qdrant or similar."""
    state["context"] = [
        "doc1: Employees are entitled to 25 vacation days per year.",
        "doc2: Sick days are capped at 3 per year without a doctor's note.",
    ]
    print(f"[retrieve] Found {len(state['context'])} docs.")
    return state


def generate(state: ReviewState) -> ReviewState:
    """Produces a draft answer. Gets better on the 2nd attempt."""
    attempts = state.get("attempts", 0)
    context_str = " ".join(state.get("context", []))

    if attempts == 0:
        # First, deliberately weak draft
        state["draft"] = "Yes."
    else:
        # After feedback we produce a better, cited answer
        state["draft"] = (
            f"According to [doc1], {state['question']} -> "
            "employees have 25 vacation days. "
            f"(context-len={len(context_str)})"
        )

    state["attempts"] = attempts + 1
    print(f"[generate] Draft #{state['attempts']}: {state['draft']!r}")
    return state


def review(state: ReviewState) -> ReviewState:
    """Rule-based reviewer. Approves if draft is long and cites a source."""
    draft = state.get("draft", "")
    has_citation = "[doc" in draft
    long_enough = len(draft) > 40

    if has_citation and long_enough:
        state["approved"] = True
        state["feedback"] = "OK"
        print(f"[review] APPROVED. attempts={state['attempts']}")
    else:
        state["approved"] = False
        state["feedback"] = "draft too short or missing citation"
        print(f"[review] REJECTED ({state['feedback']}). attempts={state['attempts']}")
    return state


# -----------------------------------------------------------------------------
# Conditional routing
# -----------------------------------------------------------------------------
def route_after_review(state: ReviewState) -> str:
    if state.get("approved"):
        return "accept"
    if state.get("attempts", 0) >= MAX_ATTEMPTS:
        return "giveup"
    return "retry"


# -----------------------------------------------------------------------------
# Build the graph
# -----------------------------------------------------------------------------
def build_graph():
    g = StateGraph(ReviewState)
    g.add_node("retrieve", retrieve)
    g.add_node("generate", generate)
    g.add_node("review", review)

    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "review")
    g.add_conditional_edges(
        "review",
        route_after_review,
        {"accept": END, "retry": "generate", "giveup": END},
    )
    return g.compile()


if __name__ == "__main__":
    app = build_graph()
    # print(app.get_graph().draw_mermaid()) # draw the graph in mermaid format
    # with open("graph.png", "wb") as f: # save the graph as a png file
    #     f.write(app.get_graph().draw_png());
    result = app.invoke(
        {
            "question": "How many vacation days do employees have?",
            "attempts": 0,
        }
    )

    print("\n========== FINAL STATE ==========")
    for k, v in result.items():
        print(f"  {k}: {v}")

    print("\n========== FINAL ANSWER ==========")
    print(result.get("draft", "<no draft>"))
