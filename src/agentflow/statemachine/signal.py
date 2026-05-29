"""EnumSignal alias and StdSignal — routing signals for the state machine.

EnumSignal is a TypeAlias for Enum used in framework signatures (Transition, run()
return type). Concrete signal sets are user-defined Enum subclasses; StdSignal
provides the universally useful ok/fail/done set.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TypeAlias

# Pattern: Marker Type Alias — gives a domain name to a stdlib type without
# introducing a new class, enabling type-checker friendly annotations.
EnumSignal: TypeAlias = Enum


class StdSignal(EnumSignal):
    """Standard signals usable by any vertex; see brief §1.3."""

    ok = auto()
    fail = auto()
    done = auto()
