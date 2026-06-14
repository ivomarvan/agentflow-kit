"""agentflow skeleton_generator — interactively generate a new project skeleton.

Usage::

    uv run python -m agentflow.skeleton_generator [output_dir]
    uv run python -m agentflow.skeleton_generator --output my_project/
    uv run python agentflow/skeleton_generator.py

Asks a few questions and writes a minimal but runnable agentflow application.
Commented-out sections in the output show alternative patterns to adapt.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class ScaffoldConfig:
    """All answers collected during the interactive session.

    Attributes:
        app_name:       Human-readable name, e.g. 'Hotel Booking'.
        class_prefix:   CamelCase prefix, e.g. 'HotelBooking'.
        module_name:    snake_case module name, e.g. 'hotel_booking'.
        description:    One-line application description.
        use_llm:        Include an LLM connector.
        use_tools:      Include ToolRegistry + tool stubs.
        use_live_model: Include LiveModel live-state viewer.
        vertex_names:   List of vertex class names.
        output_dir:     Directory where files will be written.
        multi_file:     True = project directory; False = single .py file.
    """

    app_name: str
    class_prefix: str
    module_name: str
    description: str
    use_llm: bool
    use_tools: bool
    use_live_model: bool
    vertex_names: list[str]
    output_dir: Path
    multi_file: bool


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def _ask(prompt: str, default: str = "") -> str:
    """Prompt the user for a string; return default on empty input.

    Args:
        prompt:  Text shown before the colon.
        default: Value returned when the user presses Enter without input.

    Returns:
        User input string, or default.
    """
    hint = f" [{default}]" if default else ""
    try:
        answer = input(f"  {prompt}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return answer or default


def _ask_bool(prompt: str, default: bool = True) -> bool:
    """Prompt the user for a yes/no answer.

    Args:
        prompt:  Question text (without y/n hint).
        default: Default when Enter is pressed without input.

    Returns:
        True when the user answers yes (or accepts a True default).
    """
    hint = "Y/n" if default else "y/N"
    raw = _ask(f"{prompt}? [{hint}]", "").lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def _to_class_prefix(name: str) -> str:
    """Convert a human name to CamelCase.

    Examples: ``'hotel booking'`` → ``'HotelBooking'``.

    Args:
        name: Any casing; words may be separated by spaces, underscores, or hyphens.

    Returns:
        CamelCase string.
    """
    if re.match(r"^[A-Z][a-zA-Z0-9]+$", name):
        return name
    return "".join(w.capitalize() for w in re.split(r"[\s_\-]+", name) if w)


def _to_module_name(name: str) -> str:
    """Convert a human name to snake_case.

    Examples: ``'Hotel Booking'`` → ``'hotel_booking'``.

    Args:
        name: Any casing; may contain CamelCase, spaces, or hyphens.

    Returns:
        Lowercase snake_case string.
    """
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", name)
    return re.sub(r"[\s\-]+", "_", s).lower()


# ---------------------------------------------------------------------------
# Interactive question collection
# ---------------------------------------------------------------------------

def collect_config(base_dir: Path | None) -> ScaffoldConfig:
    """Interactively collect all scaffold options and return a ScaffoldConfig.

    Args:
        base_dir: Root directory where the project (or file) will be created.
                  When None, the user is asked interactively.

    Returns:
        Fully populated ScaffoldConfig after user confirmation.
    """
    sep = "─" * 54

    print(f"\n{'═' * 54}")
    print("  agentflow Project Scaffold")
    print(f"{'═' * 54}")
    print("  Press Enter to accept the default shown in [brackets].\n")

    app_name = _ask("App name (e.g. 'Hotel Booking')", "My App")
    class_prefix = _to_class_prefix(app_name)
    module_name = _to_module_name(app_name)
    description = _ask("Short description", f"{app_name} — agentflow application")

    print()
    use_llm = _ask_bool("Use LLM (language model calls in vertices)", True)
    use_tools = (
        _ask_bool("Include ToolRegistry (functions the LLM can call)", False)
        if use_llm else False
    )
    use_live_model = _ask_bool("Include LiveModel (live-state GUI panel)", False)

    print()
    print("  Vertices are the processing nodes of the state graph.")
    print("  Example: 'Worker' or 'Intent, Collector, Executor'")
    default_verts = "Worker, Judge" if use_tools else "Worker"
    raw_verts = _ask("Vertex names (comma-separated)", default_verts)
    vertex_names = [
        (v.strip() if v.strip().endswith("Vertex") else v.strip() + "Vertex")
        for v in raw_verts.split(",")
        if v.strip()
    ]

    print()
    suggest_multi = len(vertex_names) > 1 or use_tools or use_live_model
    multi_file = _ask_bool(
        "Generate as a multi-file project directory (recommended for complex apps)",
        suggest_multi,
    )

    # Output directory: ask interactively if not provided on CLI.
    if base_dir is None:
        default_out = "examples/projects"
        raw_out = _ask("Output base directory (module subdir will be appended)", default_out)
        base_dir = Path(raw_out).resolve()
    output_dir = (base_dir / module_name) if multi_file else base_dir

    print(f"\n  {sep}")
    print("  Summary")
    print(f"  {sep}")
    print(f"  App name    : {app_name}")
    print(f"  Module      : {module_name}")
    print(f"  LLM         : {'yes' if use_llm else 'no'}")
    print(f"  Tools       : {'yes' if use_tools else 'no'}")
    print(f"  LiveModel   : {'yes' if use_live_model else 'no'}")
    print(f"  Vertices    : {', '.join(vertex_names)}")
    print(f"  Output      : {output_dir}")
    print(f"  Layout      : {'multi-file directory' if multi_file else 'single file'}")
    print(f"  {sep}")

    print()
    if not _ask_bool("Generate skeleton", True):
        print("\n  Cancelled.")
        sys.exit(0)

    return ScaffoldConfig(
        app_name=app_name,
        class_prefix=class_prefix,
        module_name=module_name,
        description=description,
        use_llm=use_llm,
        use_tools=use_tools,
        use_live_model=use_live_model,
        vertex_names=vertex_names,
        output_dir=output_dir,
        multi_file=multi_file,
    )


# ---------------------------------------------------------------------------
# Template generators
# Note: templates are written at column-0 so their content is not indented.
# ---------------------------------------------------------------------------

def _t_state(cfg: ScaffoldConfig) -> str:
    """Generate state.py — frozen dataclass state + patch + signals."""
    p = cfg.class_prefix
    signal_hints = "\n".join(
        f"    # {v.removesuffix('Vertex').lower()} = auto()"
        for v in cfg.vertex_names
    )
    return (
f'''"""State, patch and routing signals for {cfg.app_name}.

State:  frozen dataclass — immutable snapshot passed between vertices.
Patch:  mutable dataclass — vertices return (signal, patch); the runner
        merges patches into a new state via apply_patches().
Signal: Enum — determines which transition to follow after each vertex.
"""

from __future__ import annotations

import dataclasses
import operator
from enum import auto
from typing import Annotated

from agentflow.statemachine import Signal, UNSET


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class {p}Signal(Signal):
    """Routing signals emitted by {cfg.app_name} vertices."""

    ok   = auto()   # normal flow
    done = auto()   # finished successfully
    fail = auto()   # error / needs retry
    # Add domain-specific signals:
{signal_hints}


# ---------------------------------------------------------------------------
# State  (immutable — use dataclasses.replace(state, field=value))
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class {p}State:
    """Immutable state snapshot passed between vertices.

    Attributes:
        messages:       Conversation history (system + user + assistant turns).
        final_response: Final answer delivered to the user.
    """

    messages: tuple = ()
    final_response: str = ""

    # Add domain-specific fields:
    # intent: str = ""
    # user_name: str = ""
    # retry_count: int = 0


# ---------------------------------------------------------------------------
# Patch  (mutable — set only the fields you want to change)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class {p}Patch:
    """Partial update applied to {p}State after each vertex.

    Fields default to UNSET which means "do not change".
    Use Annotated[T, reducer] for accumulating fields (e.g. messages).
    """

    messages: Annotated[tuple, operator.add] | object = dataclasses.field(
        default_factory=lambda: UNSET
    )
    final_response: str | object = dataclasses.field(
        default_factory=lambda: UNSET
    )
    # Mirror every {p}State field you want to be patchable:
    # intent: str | object = dataclasses.field(default_factory=lambda: UNSET)


def initial_state(question: str, system_prompt: str = "") -> {p}State:
    """Build the initial state from the user\'s question.

    Args:
        question:      User question / prompt.
        system_prompt: Optional system instruction prepended to messages.

    Returns:
        {p}State with the message history ready for the first vertex.
    """
    msgs: list = []
    if system_prompt:
        msgs.append({{"role": "system", "content": system_prompt}})
    if question:
        msgs.append({{"role": "user", "content": question}})
    return {p}State(messages=tuple(msgs))
''')


def _t_vertices(cfg: ScaffoldConfig) -> str:
    """Generate vertices.py — LlmStateVertex implementations."""
    p = cfg.class_prefix
    base_cls = "LlmStateVertex" if cfg.use_llm else "StateVertex"
    lsv_import = "LlmStateVertex," if cfg.use_llm else "StateVertex,"

    tools_from = f"\nfrom {cfg.module_name}.tools import build_registry" if cfg.use_tools else ""

    vertex_blocks: list[str] = []
    for i, vname in enumerate(cfg.vertex_names):
        short = vname.removesuffix("Vertex")
        tools_field = (
            '\n    tools: str = "default"  # ToolRegistry key passed to Context\n'
            if cfg.use_tools else ""
        )
        achat = (
            "await ctx.llm_for_model(self.model).achat_with_tools(\n"
            "            list(state.messages),\n"
            "            registry=ctx.get_tools(self.tools),\n"
            "        )"
            if cfg.use_tools
            else "await ctx.llm_for_model(self.model).achat(list(state.messages))"
        )
        if i < len(cfg.vertex_names) - 1:
            ret_sig = f"{p}Signal.ok"
        else:
            ret_sig = f"{p}Signal.done"

        vertex_blocks.append(
f'''class {vname}({base_cls}):
    """TODO: describe what {vname} does."""
{tools_field}
    async def run(self, state: {p}State, ctx: Context) -> tuple[Signal, {p}Patch]:
        """Execute {short} logic.

        Args:
            state: Current {p}State snapshot.
            ctx:   Shared services (LLM pool, tools, event bus).

        Returns:
            Tuple of ({p}Signal, {p}Patch).
        """
        # TODO: implement {short} logic
        response = {achat}

        patch = {p}Patch(
            messages=(({{"role": "assistant", "content": response}},)),
            final_response=response,
        )
        return {ret_sig}, patch

        # --- Alternative patterns (uncomment to use) ---
        # if "error" in response.lower():
        #     return {p}Signal.fail, {p}Patch()
        # return {p}Signal.ok, {p}Patch(messages=...)
''')

    vertices_joined = "\n\n".join(vertex_blocks)

    transition_lines: list[str] = []
    # Variable names for vertex instances (reused in start= and Transition()).
    var_names = [
        vname.removesuffix("Vertex").lower() or "v"
        for vname in cfg.vertex_names
    ]
    instance_lines = "\n".join(
        f"    {var} = {vname}()"
        for var, vname in zip(var_names, cfg.vertex_names)
    )
    for i, vname in enumerate(cfg.vertex_names):
        sig = f"{p}Signal.ok" if i < len(cfg.vertex_names) - 1 else f"{p}Signal.done"
        var = var_names[i]
        next_var = var_names[i + 1] if i < len(cfg.vertex_names) - 1 else "StdEnd()"
        next_arg = next_var if next_var == "StdEnd()" else next_var
        transition_lines.append(
            f"        Transition({var}, signal={sig}, to_target={next_arg}),"
        )
    transitions_joined = "\n".join(transition_lines)

    return (
f'''"""Vertex implementations for {cfg.app_name}.

Each vertex:
  - Inherits from {base_cls} (Pydantic BaseModel).
  - Implements async run(state, ctx) -> (signal, patch).
  - Is a singleton per class in the StateGraph.
"""

from __future__ import annotations

from agentflow.statemachine import (
    Context,
    {lsv_import}
    Signal,
    StateGraph,
    StdEnd,
    Transition,
)
from {cfg.module_name}.state import {p}Patch, {p}Signal, {p}State
{tools_from}

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\\
You are a helpful assistant.
TODO: replace with your domain-specific system prompt.
"""


# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------

{vertices_joined}

# ---------------------------------------------------------------------------
# Graph — assemble the topology
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Return the assembled StateGraph for {cfg.app_name}.

    Returns:
        StateGraph ready to pass to AgentApp.
    """
{instance_lines}
    return StateGraph(
        start={var_names[0]},
        transitions=[
{transitions_joined}
            # Parallel fan-out example:
            # Transition(some_vertex, signal={p}Signal.ok,
            #            to_target=Parallel(branch_a, branch_b)),
        ],
    )
''')


def _t_tools(cfg: ScaffoldConfig) -> str:
    """Generate tools.py — used only for single-file layout (multi-file uses _t_tool_file)."""
    p = cfg.class_prefix
    return (
f'''"""Tool implementations for {cfg.app_name}.

Each tool:
  - Inherits from ToolBase.
  - Declares name, description, and parameters via param_desc().
  - Implements execute(**kwargs) -> str.
"""

from __future__ import annotations

from agentflow.tools.Tool import ToolBase, param_desc
from agentflow.tools.ToolRegistry import ToolRegistry


class ExampleTool(ToolBase):
    """A placeholder tool — replace with your domain logic."""

    name = "example_tool"
    description = "Does something useful. TODO: describe this tool."

    @param_desc(value="The input value to process.")
    def execute(self, value: str) -> str:
        """Execute the tool.

        Args:
            value: Input string to process.

        Returns:
            Result string.
        """
        # TODO: implement tool logic
        return f"Processed: {{value}}"


# Add more tools here:
# class AnotherTool(ToolBase):
#     name = "another_tool"
#     description = "..."
#
#     @param_desc(first="First parameter description.",
#                 second="Second parameter description.")
#     def execute(self, first: str, second: str) -> str:
#         ...


def build_registry() -> ToolRegistry:
    """Return the default ToolRegistry with all registered tools.

    Returns:
        ToolRegistry instance containing all tools for {cfg.app_name}.
    """
    return ToolRegistry([
        ExampleTool(),
        # AnotherTool(),
    ])
''')


def _t_vertex_file(cfg: ScaffoldConfig, vname: str, idx: int) -> str:
    """Generate vertices/<snake_name>.py for a single vertex class.

    Args:
        cfg:   Scaffold configuration.
        vname: Vertex class name, e.g. 'WorkerVertex'.
        idx:   Position in the vertex list (0-based); determines default signal.

    Returns:
        File content as a string.
    """
    p = cfg.class_prefix
    short = vname.removesuffix("Vertex")
    base_cls = "LlmStateVertex" if cfg.use_llm else "StateVertex"
    lsv_import = "LlmStateVertex," if cfg.use_llm else "StateVertex,"
    tools_field = (
        '\n    tools: str = "default"  # ToolRegistry key passed to Context\n'
        if cfg.use_tools else ""
    )
    achat = (
        "await ctx.llm_for_model(self.model).achat_with_tools(\n"
        "            list(state.messages),\n"
        "            registry=ctx.get_tools(self.tools),\n"
        "        )"
        if cfg.use_tools
        else "await ctx.llm_for_model(self.model).achat(list(state.messages))"
    )
    ret_sig = (
        f"{p}Signal.ok" if idx < len(cfg.vertex_names) - 1 else f"{p}Signal.done"
    )
    return (
f'''"""{vname} — TODO: describe what this vertex does."""

from __future__ import annotations

from agentflow.statemachine import (
    Context,
    {lsv_import}
    Signal,
)
from {cfg.module_name}.state import {p}Patch, {p}Signal, {p}State

_SYSTEM_PROMPT = """\\
You are a helpful assistant.
TODO: replace with your domain-specific system prompt for {short}.
"""


class {vname}({base_cls}):
    """TODO: describe what {vname} does."""
{tools_field}
    async def run(self, state: {p}State, ctx: Context) -> tuple[Signal, {p}Patch]:
        """Execute {short} logic.

        Args:
            state: Current {p}State snapshot.
            ctx:   Shared services (LLM pool, tools, event bus).

        Returns:
            Tuple of ({p}Signal, {p}Patch).
        """
        # TODO: implement {short} logic
        response = {achat}

        patch = {p}Patch(
            messages=(({{\"role\": \"assistant\", \"content\": response}},)),
            final_response=response,
        )
        return {ret_sig}, patch

        # --- Alternative patterns (uncomment to use) ---
        # if "error" in response.lower():
        #     return {p}Signal.fail, {p}Patch()
        # return {p}Signal.ok, {p}Patch(messages=...)
''')


def _t_vertices_init(cfg: ScaffoldConfig) -> str:
    """Generate vertices/__init__.py — re-exports all vertex classes.

    Args:
        cfg: Scaffold configuration.

    Returns:
        File content as a string.
    """
    imports = "\n".join(
        f"from .{_to_module_name(vname)} import {vname}"
        for vname in cfg.vertex_names
    )
    all_list = ", ".join(f'"{v}"' for v in cfg.vertex_names)
    return (
f'''"""Vertices package for {cfg.app_name}.

Import all vertex classes from their individual modules.
Add new vertices by creating <snake_name>.py and importing here.
"""

{imports}

__all__ = [{all_list}]
''')


def _t_tool_file(cfg: ScaffoldConfig) -> str:
    """Generate tools/example_tool.py — placeholder tool for multi-file layout.

    Args:
        cfg: Scaffold configuration.

    Returns:
        File content as a string.
    """
    return (
f'''"""ExampleTool — replace with your domain tool implementation."""

from __future__ import annotations

from agentflow.tools.Tool import ToolBase, param_desc


class ExampleTool(ToolBase):
    """A placeholder tool — replace with your domain logic."""

    name = "example_tool"
    description = "Does something useful. TODO: describe this tool."

    @param_desc(value="The input value to process.")
    def execute(self, value: str) -> str:
        """Execute the tool.

        Args:
            value: Input string to process.

        Returns:
            Result string.
        """
        # TODO: implement tool logic
        return f"Processed: {{value}}"
''')


def _t_tools_init(cfg: ScaffoldConfig) -> str:
    """Generate tools/__init__.py — re-exports all tool classes.

    Args:
        cfg: Scaffold configuration.

    Returns:
        File content as a string.
    """
    return (
f'''"""Tools package for {cfg.app_name}.

Import all tool classes from their individual modules.
Add new tools by creating <snake_name>.py and importing here.
"""

from .example_tool import ExampleTool

__all__ = ["ExampleTool"]
''')


def _t_live_model(cfg: ScaffoldConfig) -> str:
    """Generate {module}_model.py — LiveModel with @action stubs."""
    p = cfg.class_prefix
    return (
f'''"""{p}Model — LiveModel for {cfg.app_name}.

Run standalone (no LLM) to test the visual state panel:
    uv run python {cfg.module_name}/{cfg.module_name}_model.py

Use in AgentApp:
    from {cfg.module_name}.{cfg.module_name}_model import {p}Model
    model = {p}Model()
    app = AgentApp(live_model=model, ...)
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from agentflow.live_model import LiveModel, action


# ---------------------------------------------------------------------------
# Live state  (Pydantic BaseModel — rendered by the GUI state panel)
# ---------------------------------------------------------------------------

class {p}LiveState(BaseModel):
    """Live state snapshot displayed in the GUI state panel.

    Add fields that should be visible in the live-state viewer.
    """

    model_config = ConfigDict(frozen=False)

    # TODO: replace with your domain state fields
    status: str = "idle"
    last_action: str = ""
    items: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LiveModel
# ---------------------------------------------------------------------------

class {p}Model(LiveModel):
    """Self-describing {cfg.app_name} model with @action API.

    Run as standalone demo:
        python {cfg.module_name}/{cfg.module_name}_model.py
    """

    def __init__(self) -> None:
        self._state = {p}LiveState()

    @property
    def state(self) -> {p}LiveState:
        """Current live state snapshot."""
        return self._state

    @action
    def do_something(
        self,
        value: Annotated[str, Field(description="Input value to process.")],
    ) -> str:
        """Perform an action — TODO: replace with domain logic."""
        self._state.last_action = f"do_something({{value}})"
        self._state.items.append(value)
        return f"Done: {{value}}"

    # --- More @action examples ---
    #
    # @action
    # def reset(self) -> str:
    #     """Reset the model state."""
    #     self._state = {p}LiveState()
    #     return "Reset."
    #
    # @action
    # def pick_date(
    #     self,
    #     date: Annotated[
    #         str,
    #         Field(description="Date (YYYY-MM-DD).",
    #               json_schema_extra={{"x-widget": "date"}}),
    #     ],
    # ) -> str:
    #     """Store a date."""
    #     self._state.last_action = f"date={{date}}"
    #     return f"Date set: {{date}}"


if __name__ == "__main__":
    {p}Model.demo()
''')


def _t_app_multifile(cfg: ScaffoldConfig) -> str:
    """Generate the main app entry point for a multi-file project.

    Includes build_graph() (state graph topology) and build_registry() (tool
    registry) inline so that the individual vertex/tool files stay focused on
    their single responsibility.
    """
    p = cfg.class_prefix

    # Vertex variable names (one instance per class, reused in start= and Transition).
    var_names = [
        v.removesuffix("Vertex").lower() or "v"
        for v in cfg.vertex_names
    ]
    instance_lines = "\n".join(
        f"    {var} = {vname}()"
        for var, vname in zip(var_names, cfg.vertex_names)
    )

    # Vertex imports from the vertices/ sub-package.
    vertex_imports = "\n".join(
        f"from {cfg.module_name}.vertices.{_to_module_name(v)} import {v}"
        for v in cfg.vertex_names
    )

    # Transition lines for build_graph().
    transition_lines: list[str] = []
    for i, vname in enumerate(cfg.vertex_names):
        sig = f"{p}Signal.ok" if i < len(cfg.vertex_names) - 1 else f"{p}Signal.done"
        var = var_names[i]
        next_arg = var_names[i + 1] if i < len(cfg.vertex_names) - 1 else "StdEnd()"
        transition_lines.append(
            f"        Transition({var}, signal={sig}, to_target={next_arg}),"
        )
    transitions_joined = "\n".join(transition_lines)
    lsv_import = "LlmStateVertex," if cfg.use_llm else "StateVertex,"

    # Tools section (build_registry inline).
    if cfg.use_tools:
        tools_import = f"from {cfg.module_name}.tools.example_tool import ExampleTool"
        registry_import = "\nfrom agentflow.tools.ToolRegistry import ToolRegistry"
        context_extra = f'\n        tool_registries={{"default": build_registry()}},'
        build_registry_fn = (
f'''

def build_registry() -> ToolRegistry:
    """Return the default ToolRegistry.

    Returns:
        ToolRegistry with all registered tools.
    """
    return ToolRegistry([
        ExampleTool(),
        # Add more tools here and import them above.
    ])''')
    else:
        tools_import = ""
        registry_import = ""
        context_extra = ""
        build_registry_fn = ""

    live_model_import = (
        f"\nfrom {cfg.module_name}.{cfg.module_name}_model import {p}Model"
        if cfg.use_live_model else ""
    )
    live_model_line = (
        f"\n    live_model={p}Model(),"
        if cfg.use_live_model
        else f"\n    # live_model={p}Model(),  # uncomment to enable live-state panel"
    )

    return (
f'''"""{cfg.description}

Run:
    uv run python {cfg.module_name}/{cfg.module_name}_app.py run "Hello"
    uv run python {cfg.module_name}/{cfg.module_name}_app.py gui
    uv run python {cfg.module_name}/{cfg.module_name}_app.py graph --browser
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to sys.path so the package is importable regardless of
# which directory the script is invoked from.
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentflow import AgentApp
from agentflow.llm.LlmPool import LlmPool
from agentflow.statemachine import (
    Context,
    {lsv_import}
    Signal,
    StateGraph,
    StdEnd,
    Transition,
){registry_import}
from {cfg.module_name}.state import {p}Signal, initial_state
{vertex_imports}
{tools_import}{live_model_import}

# ---------------------------------------------------------------------------
# Graph topology — assembled here so vertex files stay focused on logic
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Return the assembled StateGraph for {cfg.app_name}.

    Returns:
        StateGraph ready to pass to AgentApp.
    """
{instance_lines}
    return StateGraph(
        start={var_names[0]},
        transitions=[
{transitions_joined}
            # Parallel fan-out example:
            # Transition(some_vertex, signal={p}Signal.ok,
            #            to_target=Parallel(branch_a, branch_b)),
        ],
    )
{build_registry_fn}

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

_SAMPLE_PROMPTS = [
    "Hello, what can you do?",
    "TODO: add representative example prompts here",
]

_APP = AgentApp(
    doc=__doc__,
    context=Context(
        pool=LlmPool(),{context_extra}
    ),
    state_graph=build_graph(),
    initial_state_factory=lambda q: initial_state(q),{live_model_line}
    sample_prompts=_SAMPLE_PROMPTS,
)


if __name__ == "__main__":
    _APP.cli(__doc__, name=__name__)
''')


def _t_app_single(cfg: ScaffoldConfig) -> str:
    """Generate a complete single-file skeleton."""
    p = cfg.class_prefix
    v0 = cfg.vertex_names[0] if cfg.vertex_names else "WorkerVertex"

    # --- conditional blocks ---
    tools_block = ""
    if cfg.use_tools:
        tools_block = (
f'''

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class ExampleTool(ToolBase):
    """TODO: replace with your domain tool."""

    name = "example_tool"
    description = "Does something useful."

    @param_desc(value="The input value.")
    def execute(self, value: str) -> str:
        return f"Result: {{value}}"


_REGISTRY = ToolRegistry([ExampleTool()])
''')

    live_model_block = ""
    if cfg.use_live_model:
        live_model_block = (
f'''

# ---------------------------------------------------------------------------
# LiveModel  (live state panel in the GUI)
# ---------------------------------------------------------------------------

class {p}LiveState(BaseModel):
    model_config = ConfigDict(frozen=False)
    status: str = "idle"


class {p}Model(LiveModel):
    """Standalone: python {cfg.module_name}.py (runs LiveModel.demo())"""

    def __init__(self) -> None:
        self._state = {p}LiveState()

    @property
    def state(self) -> {p}LiveState:
        return self._state

    @action
    def set_status(self, status: str) -> str:
        """Update the status label."""
        self._state.status = status
        return f"Status: {{status}}"
''')

    tools_imports = (
        "from agentflow.tools.Tool import ToolBase, param_desc\n"
        "from agentflow.tools.ToolRegistry import ToolRegistry\n"
        if cfg.use_tools else ""
    )
    live_model_imports = (
        "from pydantic import BaseModel, ConfigDict\n"
        "from agentflow.live_model import LiveModel, action\n"
        if cfg.use_live_model else ""
    )
    context_extra = (
        '\n        tool_registries={"default": _REGISTRY},'
        if cfg.use_tools else ""
    )
    live_model_line = (
        f"\n    live_model={p}Model(),"
        if cfg.use_live_model
        else "\n    # live_model=MyModel(),  # uncomment to enable live-state panel"
    )
    achat = (
        "await ctx.llm_for_model(self.model).achat_with_tools(\n"
        "            list(state.messages),\n"
        "            registry=ctx.get_tools(self.tools),\n"
        "        )"
        if cfg.use_tools
        else "await ctx.llm_for_model(self.model).achat(list(state.messages))"
    )
    tools_field = (
        '\n    tools: str = "default"  # ToolRegistry key passed to Context\n'
        if cfg.use_tools else ""
    )
    base_cls = "LlmStateVertex" if cfg.use_llm else "StateVertex"
    lsv_import = "LlmStateVertex," if cfg.use_llm else "StateVertex,"

    return (
f'''"""{cfg.description}

Run:
    uv run python {cfg.module_name}.py run "Hello"
    uv run python {cfg.module_name}.py gui
"""

from __future__ import annotations

import dataclasses
import operator
from enum import auto
from typing import Annotated

from agentflow import AgentApp
from agentflow.llm.LlmPool import LlmPool
from agentflow.statemachine import (
    Context,
    {lsv_import}
    Signal,
    StateGraph,
    StdEnd,
    Transition,
    UNSET,
)
{tools_imports}{live_model_imports}
# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\\
You are a helpful assistant.
TODO: replace with your domain-specific system prompt.
"""


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class {p}Signal(Signal):
    ok   = auto()
    done = auto()
    fail = auto()


# ---------------------------------------------------------------------------
# State + Patch
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class {p}State:
    messages: tuple = ()
    final_response: str = ""


@dataclasses.dataclass
class {p}Patch:
    messages: Annotated[tuple, operator.add] | object = dataclasses.field(
        default_factory=lambda: UNSET
    )
    final_response: str | object = dataclasses.field(
        default_factory=lambda: UNSET
    )
{tools_block}{live_model_block}

# ---------------------------------------------------------------------------
# Vertices
# ---------------------------------------------------------------------------

class {v0}({base_cls}):
    """Main processing vertex — TODO: implement your logic here."""
{tools_field}
    async def run(self, state: {p}State, ctx: Context) -> tuple[Signal, {p}Patch]:
        """Run the main logic."""
        response = {achat}
        patch = {p}Patch(
            messages=(({{"role": "assistant", "content": response}},)),
            final_response=response,
        )
        return {p}Signal.done, patch

        # --- Patterns (uncomment to use) ---
        # if "error" in response.lower():
        #     return {p}Signal.fail, {p}Patch()
        # return {p}Signal.ok, patch


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

_v0 = {v0}()
_GRAPH = StateGraph(
    start=_v0,
    transitions=[
        Transition(_v0, signal={p}Signal.done, to_target=StdEnd()),
        # Transition(_v0, signal={p}Signal.fail, to_target=StdEnd()),
    ],
)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

_APP = AgentApp(
    doc=__doc__,
    system_prompt=_SYSTEM_PROMPT,
    context=Context(
        pool=LlmPool(),{context_extra}
    ),
    state_graph=_GRAPH,{live_model_line}
    sample_prompts=["Hello", "TODO: add example prompts"],
)


if __name__ == "__main__":
    _APP.cli(__doc__, name=__name__)
''')


def _t_readme(cfg: ScaffoldConfig) -> str:
    """Generate README.md for the project."""
    if cfg.multi_file:
        files = f"- `{cfg.module_name}_app.py` — entry point, graph topology, tool registry\n"
        files += "- `state.py` — state dataclass, patch, and signals\n"
        files += "- `vertices/` — one file per vertex class\n"
        if cfg.use_tools:
            files += "- `tools/` — one file per tool class\n"
        if cfg.use_live_model:
            files += f"- `{cfg.module_name}_model.py` — LiveModel live-state viewer\n"
    else:
        files = f"- `{cfg.module_name}.py` — single-file application\n"

    run = (
        f"uv run python {cfg.module_name}/{cfg.module_name}_app.py run \"Hello\"\n"
        if cfg.multi_file
        else f"uv run python {cfg.module_name}.py run \"Hello\"\n"
    )
    gui = (
        f"uv run python {cfg.module_name}/{cfg.module_name}_app.py gui"
        if cfg.multi_file
        else f"uv run python {cfg.module_name}.py gui"
    )

    extras = "- GUI server (`gui` subcommand)\n"
    if cfg.use_tools:
        extras += "- Tool calling via `ToolRegistry`\n"
    if cfg.use_live_model:
        extras += "- `LiveModel` live-state GUI panel\n"

    if cfg.multi_file:
        nextsteps = "1. Edit each vertex in `vertices/` — replace the system prompt and logic.\n"
        nextsteps += "2. Add vertex classes: create a new file in `vertices/`, import it in `vertices/__init__.py`,\n"
        nextsteps += f"   then add a `Transition` in `build_graph()` in `{cfg.module_name}_app.py`.\n"
        nextsteps += f"3. Extend `{cfg.class_prefix}State` in `state.py` with domain-specific fields.\n"
        if cfg.use_tools:
            nextsteps += "4. Add tool classes in `tools/`, import them in `tools/__init__.py`,\n"
            nextsteps += f"   then register them in `build_registry()` in `{cfg.module_name}_app.py`.\n"
    else:
        nextsteps = "1. Replace `_SYSTEM_PROMPT` with your domain prompt.\n"
        nextsteps += "2. Add / rename vertex classes to match your workflow.\n"
        nextsteps += f"3. Extend `{cfg.class_prefix}State` with domain-specific fields.\n"
        if cfg.use_tools:
            nextsteps += "4. Implement tools in the tools section.\n"
    if cfg.use_live_model:
        nextsteps += f"5. Add `@action` methods to `{cfg.class_prefix}Model`.\n"

    return (
f'''# {cfg.app_name}

{cfg.description}

## Files

{files}
## Run

```bash
# CLI run
{run}# GUI server
{gui}
```

## Concepts demonstrated

- Declarative `AgentApp` with `StateGraph`
- Typed state (frozen dataclass) + patch + signal routing
{extras}
## Next steps

{nextsteps}''')


def _t_init(cfg: ScaffoldConfig) -> str:
    """Generate __init__.py for the project package."""
    return (
f'''"""{cfg.description}"""

from {cfg.module_name}.{cfg.module_name}_app import _APP as app

__all__ = ["app"]
''')


# ---------------------------------------------------------------------------
# File generation
# ---------------------------------------------------------------------------

def generate(cfg: ScaffoldConfig) -> None:
    """Write all scaffold files to disk based on the config.

    For multi-file layout the structure is:
      <module>/
        <module>_app.py     — entry point + build_graph() + build_registry()
        state.py            — State, Patch, Signal
        vertices/
          __init__.py       — re-exports all vertex classes
          <vertex>.py       — one file per vertex
        tools/              — (only when use_tools)
          __init__.py
          example_tool.py
        <module>_model.py   — (only when use_live_model)
        __init__.py
        README.md

    Args:
        cfg: Fully populated ScaffoldConfig from collect_config().
    """
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    # Map relative path → content.
    files: dict[str, str] = {}

    if cfg.multi_file:
        files[f"{cfg.module_name}_app.py"] = _t_app_multifile(cfg)
        files["state.py"] = _t_state(cfg)
        # One file per vertex in vertices/
        for i, vname in enumerate(cfg.vertex_names):
            snake = _to_module_name(vname)
            files[f"vertices/{snake}.py"] = _t_vertex_file(cfg, vname, i)
        files["vertices/__init__.py"] = _t_vertices_init(cfg)
        # One file per tool in tools/
        if cfg.use_tools:
            files["tools/example_tool.py"] = _t_tool_file(cfg)
            files["tools/__init__.py"] = _t_tools_init(cfg)
        if cfg.use_live_model:
            files[f"{cfg.module_name}_model.py"] = _t_live_model(cfg)
        files["__init__.py"] = _t_init(cfg)
        files["README.md"] = _t_readme(cfg)
    else:
        files[f"{cfg.module_name}.py"] = _t_app_single(cfg)

    created: list[Path] = []
    skipped: list[Path] = []

    for filename, content in files.items():
        target = cfg.output_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            skipped.append(target)
        else:
            target.write_text(content, encoding="utf-8")
            created.append(target)

    print(f"\n  {'─' * 54}")
    print(f"  Created {len(created)} file(s) in: {cfg.output_dir}")
    for p in created:
        print(f"    + {p.relative_to(cfg.output_dir.parent)}")
    if skipped:
        print(f"  Skipped {len(skipped)} (already exist):")
        for p in skipped:
            print(f"    ! {p.relative_to(cfg.output_dir.parent)}")
    print()

    if cfg.multi_file:
        rel_path = f"{cfg.module_name}/{cfg.module_name}_app.py"
    else:
        rel_path = f"{cfg.module_name}.py"
    print("  Quick start:")
    print(f'    uv run python {rel_path} run "Hello"')
    print(f"    uv run python {rel_path} gui")
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse CLI arguments and run the interactive scaffold generator."""
    parser = argparse.ArgumentParser(
        prog="python -m agentflow.skeleton_generator",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        default=None,
        help="Base directory for the new project (default: current directory).",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        dest="output_flag",
        metavar="DIR",
        help="Alternative way to specify the base output directory.",
    )
    args, _ = parser.parse_known_args()

    # When output is given on CLI, resolve it; otherwise let collect_config ask.
    if args.output_dir or args.output_flag:
        base_dir: Path | None = (args.output_dir or args.output_flag).resolve()
    else:
        base_dir = None

    cfg = collect_config(base_dir)
    generate(cfg)


if __name__ == "__main__":
    main()
