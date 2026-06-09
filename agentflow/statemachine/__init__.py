"""agentflow.statemachine — declarative state graph orchestration for AI agents.

Public API grows incrementally with each Task of Epic E010-E070 (see roadmap.md).
Current exports (after E103-T02): Signal, EnumSignal, StdSignal, apply_patches, UNSET, Context,
RunStats, StateVertex, End, StdEnd, RunnerHooks, NoOpHooks, LoggingHooks, RecorderHooks,
SuperStepRecord, LiveGraphHooks, Transition, Parallel, StateGraph, StateGraphRunner,
VertexResolver, ToolCallVertex, LlmTurnVertex, ToolAgentVertex,
CheckpointRecord, CheckpointStore, InMemoryCheckpointStore, JsonFileCheckpointStore,
PostgresCheckpointStore, RedisCheckpointStore,
ReActState, ReActPatch, ReActSignal, ToolCallInfo (ReAct variant).
"""

from enum import Enum as Signal  # allow: class MySignal(Signal): ...

from agentflow.statemachine.adapters import LlmTurnVertex, ToolAgentVertex, ToolCallVertex
from agentflow.statemachine.backends.postgres_checkpoint_store import (
    PostgresCheckpointStore,
)
from agentflow.statemachine.backends.redis_checkpoint_store import (
    RedisCheckpointStore,
)
from agentflow.statemachine.checkpoint import (
    CheckpointRecord,
    CheckpointStore,
    InMemoryCheckpointStore,
    JsonFileCheckpointStore,
)
from agentflow.statemachine.context import Context
from agentflow.statemachine.hooks import (
    LiveGraphHooks,
    LoggingHooks,
    NoOpHooks,
    RecorderHooks,
    RunnerHooks,
    SuperStepRecord,
)
from agentflow.statemachine.react import ReActPatch, ReActSignal, ReActState, ToolCallInfo
from agentflow.statemachine.resolver import VertexResolver
from agentflow.statemachine.run_stats import RunStats
from agentflow.statemachine.runner import StateGraphRunner
from agentflow.statemachine.signal import EnumSignal, StdSignal
from agentflow.statemachine.state import UNSET, apply_patches
from agentflow.statemachine.topology import Parallel, StateGraph, Transition
from agentflow.statemachine.vertex import End, LlmStateVertex, StateVertex, StdEnd

__all__ = [
    "CheckpointRecord",
    "CheckpointStore",
    "Context",
    "End",
    "LlmStateVertex",
    "EnumSignal",
    "ReActPatch",
    "ReActSignal",
    "ReActState",
    "Signal",
    "ToolCallInfo",
    "InMemoryCheckpointStore",
    "JsonFileCheckpointStore",
    "LiveGraphHooks",
    "LlmTurnVertex",
    "LoggingHooks",
    "NoOpHooks",
    "Parallel",
    "PostgresCheckpointStore",
    "RecorderHooks",
    "RedisCheckpointStore",
    "RunnerHooks",
    "RunStats",
    "StateGraph",
    "StateGraphRunner",
    "StdEnd",
    "StdSignal",
    "StateVertex",
    "SuperStepRecord",
    "ToolAgentVertex",
    "ToolCallVertex",
    "Transition",
    "UNSET",
    "VertexResolver",
    "apply_patches",
]
