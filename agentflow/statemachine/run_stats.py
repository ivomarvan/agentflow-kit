"""RunStats — accumulated token usage and timing for a single graph run."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentflow.llm.ChatResponse import UsageInfo


@dataclass
class RunStats:
    """Accumulated statistics for one AgentApp run.

    Updated automatically by _TrackedConnector (context.py) after each LLM call.
    Available via ctx.stats and returned by AgentApp.run_and_stats().

    Attributes:
        total_tokens:       Sum of prompt + completion tokens across all models.
        prompt_tokens:      Tokens in all LLM prompts.
        completion_tokens:  Tokens in all LLM completions.
        wall_time_ms:       Total wall-clock time (ms) from run start to finish.
        llm_calls:          Number of LLM calls (cache miss or no cache).
        cache_hits:         Number of responses served from cache.
        by_model:           Per-model token usage: model -> {prompt, completion, total, calls}.
    """

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_time_ms: float = 0.0
    llm_calls: int = 0
    cache_hits: int = field(default=0)
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, model: str, usage: UsageInfo | None, *, cache_hit: bool = False) -> None:
        """Accumulate token usage for one LLM call.

        Args:
            model:     Model identifier (e.g. 'gpt-4o-mini').
            usage:     UsageInfo from ChatResponse; None if not available (skipped).
            cache_hit: True when the response was served from cache.
        """
        if cache_hit:
            self.cache_hits += 1
        else:
            self.llm_calls += 1

        if usage is None:
            return

        self.total_tokens += usage.total_tokens
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens

        if model not in self.by_model:
            self.by_model[model] = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
        bucket = self.by_model[model]
        bucket["prompt"] += usage.prompt_tokens
        bucket["completion"] += usage.completion_tokens
        bucket["total"] += usage.total_tokens
        bucket["calls"] += 1
