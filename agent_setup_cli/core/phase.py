"""
Phase-Fluid Agent Architecture (PFAA) — Phase Definitions

Agents exist in three execution phases and transition between them
based on task characteristics, resource pressure, and self-profiling.

    VAPOR   → async coroutine  (~1μs spawn, shared memory, I/O-bound)
    LIQUID  → OS thread        (~10μs spawn, shared memory, CPU-parallel)
    SOLID   → subprocess       (~1ms spawn, isolated memory, crash-safe)

Phase transitions:
    VAPOR  →  LIQUID   = condense  (task needs CPU)
    LIQUID →  SOLID    = freeze    (task needs isolation)
    SOLID  →  LIQUID   = melt      (isolation no longer needed)
    LIQUID →  VAPOR    = evaporate (task returns to I/O)
    VAPOR  →  SOLID    = sublimate (skip liquid, go straight to isolation)
    SOLID  →  VAPOR    = deposit   (process done, return to coroutine)
"""

from enum import Enum, auto
from typing import NamedTuple


class Phase(Enum):
    VAPOR = auto()    # async coroutine
    LIQUID = auto()   # free thread
    SOLID = auto()    # subprocess

    @property
    def spawn_cost_us(self) -> int:
        return {Phase.VAPOR: 1, Phase.LIQUID: 10, Phase.SOLID: 1000}[self]

    @property
    def parallelism(self) -> str:
        return {
            Phase.VAPOR: "cooperative (I/O)",
            Phase.LIQUID: "preemptive (CPU)",
            Phase.SOLID: "isolated (process)",
        }[self]


class Transition(NamedTuple):
    from_phase: Phase
    to_phase: Phase
    reason: str


TRANSITIONS = {
    "condense":  Transition(Phase.VAPOR,  Phase.LIQUID, "task needs CPU parallelism"),
    "freeze":    Transition(Phase.LIQUID, Phase.SOLID,  "task needs crash isolation"),
    "melt":      Transition(Phase.SOLID,  Phase.LIQUID, "isolation no longer needed"),
    "evaporate": Transition(Phase.LIQUID, Phase.VAPOR,  "task returns to I/O-bound"),
    "sublimate": Transition(Phase.VAPOR,  Phase.SOLID,  "direct to isolation"),
    "deposit":   Transition(Phase.SOLID,  Phase.VAPOR,  "process done, lighten"),
}
