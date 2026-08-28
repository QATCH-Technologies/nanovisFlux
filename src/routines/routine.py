from __future__ import annotations

from dataclasses import dataclass, field

from ..core import MountSide
from .steps import Step


@dataclass
class Routine:
    """Ordered, inspectable sequence of robot execution steps.

    A routine is constructed as a sequence of :class:`Step` objects that can
    be inspected, described for a dry run, validated, logged, or potentially
    serialized independently of execution. Hardware interaction occurs only
    when :meth:`run` is called.

    The `side` attribute specifies the mount used at the start of execution.
    It does not permanently constrain the routine to that mount. If a step
    returns a :class:`MountSide`, such as a mount-switching step, that value
    becomes the active mount for all subsequent steps. Consequently, a single
    routine may operate across multiple mounts.

    Attributes:
        name: Human-readable name identifying the routine.
        side: Mount used when execution begins unless overridden by the
            `side` argument to :meth:`run`.
        steps: Ordered collection of steps to execute.
    """

    name: str = "routine"
    side: MountSide = MountSide.LEFT
    steps: list = field(default_factory=list)

    def add(self, *steps: Step) -> Routine:
        """Append one or more steps to the routine.

        Steps are appended in the order provided. The routine itself is returned,
        allowing calls to be chained when constructing a routine.

        Args:
            *steps: Step objects to append to the routine.

        Returns:
            Routine: This routine instance.
        """
        self.steps.extend(steps)
        return self

    def extend(self, steps) -> Routine:
        """Append an iterable of steps to the routine.

        The steps are appended in their existing iteration order. The routine
        itself is returned to support fluent routine construction.

        Args:
            steps: Iterable of :class:`Step` objects to append.

        Returns:
            Routine: This routine instance.
        """
        self.steps.extend(steps)
        return self

    def dry_run(self) -> list:
        """Generate a human-readable execution plan without using hardware.

        Each step is converted to its descriptive representation and prefixed
        with its one-based position in the routine. No step is executed and no
        robot instance is required.

        Returns:
            list[str]: Ordered, human-readable descriptions of the routine's
            steps.
        """
        return [f"{i + 1:>2}. {s.describe()}" for i, s in enumerate(self.steps)]

    def run(self, robot, side: MountSide | None = None, *, on_step=None) -> None:
        """Execute the routine sequentially against a robot.

        Execution begins using the explicitly supplied `side` when provided;
        otherwise, the routine's configured :attr:`side` is used. Before each
        step executes, the optional `on_step` callback is invoked with the
        step's zero-based index and the step object.

        A step may return a :class:`MountSide` to indicate that subsequent steps
        should execute using a different mount. This allows mount-switching steps
        to change the active mount for the remainder of the routine without
        requiring the routine itself to be permanently associated with one mount.

        Args:
            robot: Robot instance against which the routine's steps are executed.
            side: Optional initial mount override. If `None`, the routine's
                configured :attr:`side` is used.
            on_step: Optional callback invoked immediately before each step is
                executed. The callback receives the step's zero-based index and
                the step object.

        Returns:
            None

        Raises:
            Exception: Any exception raised by a step or by the `on_step`
                callback propagates to the caller.
        """
        current = side or self.side
        for i, step in enumerate(self.steps):
            if on_step:
                on_step(i, step)
            result = step.execute(robot, current)
            if isinstance(result, MountSide):
                current = result
