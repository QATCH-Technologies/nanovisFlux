from __future__ import annotations

from dataclasses import dataclass, field

from ..core import MountSide
from .steps import Step


@dataclass
class Routine:
    """An ordered, inspectable list of Steps. Build it, print it (dry run),
    then run it. Because steps are objects it is trivial to log, validate or
    later serialise a routine to/from YAML.

    ``side`` is only the STARTING mount -- a routine isn't pinned to one
    side for its whole run: a SwitchMountStep anywhere in ``steps`` changes
    which mount every step after it addresses (see run() and
    SwitchMountStep's own docstring), so one routine can freely act on
    more than one mount instead of needing to be written "for" a specific
    one. Leave a routine that never switches exactly as side-specific as
    before -- this is purely additive."""

    name: str = "routine"
    side: MountSide = MountSide.LEFT
    steps: list = field(default_factory=list)

    def add(self, *steps: Step) -> "Routine":
        self.steps.extend(steps)
        return self

    def extend(self, steps) -> "Routine":
        self.steps.extend(steps)
        return self

    def dry_run(self) -> list:
        """Return the human-readable plan without touching hardware."""
        return [f"{i + 1:>2}. {s.describe()}" for i, s in enumerate(self.steps)]

    def run(self, robot, side: MountSide | None = None, *, on_step=None) -> None:
        current = side or self.side
        for i, step in enumerate(self.steps):
            if on_step:
                on_step(i, step)
            result = step.execute(robot, current)
            if isinstance(result, MountSide):
                current = result
