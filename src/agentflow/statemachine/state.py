"""State, StatePatch and per-field reducer dispatch.

Standalone helper functions for applying patches to frozen dataclass states.
User-defined State classes remain plain frozen dataclasses — no framework
base class required (see spec.md TD-14).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Sequence
from typing import Annotated, Any, TypeVar, get_args, get_origin, get_type_hints

# Sentinel — distinguishes "not set in this patch" from "explicitly set to None".
# Use as default value in StatePatch fields where None is a valid domain value.
UNSET: object = object()

_logger = logging.getLogger(__name__)

S = TypeVar("S")


def extract_reducer(annotated_type: Any) -> Callable[[Any, Any], Any] | None:
    """Return the reducer callable from an Annotated[T, reducer] type, or None.

    Args:
        annotated_type: A type annotation, potentially Annotated[T, reducer].

    Returns:
        The reducer callable if the first metadata argument is callable,
        otherwise None.
    """
    if get_origin(annotated_type) is not Annotated:
        return None
    args = get_args(annotated_type)
    if len(args) < 2:
        return None
    candidate = args[1]
    if callable(candidate):
        return candidate  # type: ignore[no-any-return]
    return None


def apply_patches(state: S, patches: Sequence[Any]) -> S:
    """Merge a sequence of StatePatch objects into a new state instance.

    For each field:
    - If annotated with Annotated[T, reducer]: calls reducer(accumulated, new) for
      each patch that sets the field (non-None, non-UNSET).
    - If no reducer: last-writer-wins; emits WARNING when multiple patches write
      the same field with different non-None values (non-deterministic merge).
    - None in a patch field means "do not set" (skip).
    - UNSET sentinel means "do not set" (skip).

    Args:
        state: Current frozen dataclass instance.
        patches: Sequence of StatePatch-like objects (frozen dataclasses with
                 Optional fields defaulting to None).

    Returns:
        New state instance with all patch contributions merged.
        Returns the same state object when patches is empty or all patch fields
        are None/UNSET.

    Raises:
        TypeError: If state is not a dataclass instance.
    """
    if not dataclasses.is_dataclass(state) or isinstance(state, type):
        raise TypeError(f"state must be a dataclass instance, got {type(state)!r}")

    if not patches:
        return state

    hints = get_type_hints(type(state), include_extras=True)
    updates: dict[str, Any] = {}

    for field in dataclasses.fields(state):
        name = field.name
        hint = hints.get(name)
        reducer = extract_reducer(hint) if hint is not None else None

        accumulated: Any = getattr(state, name)
        last_written: Any = UNSET
        had_reducer_write = False

        for patch in patches:
            patch_val = getattr(patch, name, UNSET)
            if patch_val is UNSET or patch_val is None:
                continue

            if reducer is not None:
                accumulated = reducer(accumulated, patch_val)
                had_reducer_write = True
            else:
                if last_written is not UNSET and patch_val != last_written:
                    _logger.warning(
                        "Non-deterministic merge: field=%s written by multiple patches "
                        "without a reducer; last-writer-wins applied",
                        name,
                    )
                last_written = patch_val
                accumulated = patch_val

        if had_reducer_write or last_written is not UNSET:
            updates[name] = accumulated

    if not updates:
        return state

    return dataclasses.replace(state, **updates)
