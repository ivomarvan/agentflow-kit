"""RunStats — accumulated token usage and timing for a single graph run."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunStats:
    """Accumulated statistics for one AgentApp run.

    Updated automatically by LlmConnectorBase after each LLM call.
    Available via ctx.stats and returned by AgentApp.run_and_stats().

    Attributes:
        total_tokens:       Sum of prompt + completion tokens.
        prompt_tokens:      Tokens in all LLM prompts.
        completion_tokens:  Tokens in all LLM completions.
        wall_time_ms:       Total wall-clock time (ms) from run start to finish.
        llm_calls:          Number of LLM calls (cache miss or no cache).
        cache_hits:         Number of responses served from cache.
    """

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_time_ms: float = 0.0
    llm_calls: int = 0
    cache_hits: int = field(default=0)
