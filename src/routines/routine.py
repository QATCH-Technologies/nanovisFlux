from __future__ import annotations
from dataclasses import dataclass, field
from ..core import MountSide
from .steps import Step


@dataclass
class Routine:
    """An ordered, inspectable list of Steps. Build it, print it (dry run),
    then run it. Because steps are objects it is trivial to log, validate or
    later serialise a routine to/from YAML."""
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
        side = side or self.side
        for i, step in enumerate(self.steps):
            if on_step:
                on_step(i, step)
            step.execute(robot, side)
