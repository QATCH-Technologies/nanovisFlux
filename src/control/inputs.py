"""Input-source abstractions for jog control.

This module defines the interface used by jog-session input backends and
provides a dependency-free scripted implementation for tests, demonstrations,
and deterministic motion sequences.

Concrete interactive backends, such as keyboard and gamepad input, implement
the :class:`InputSource` interface and translate physical controls into jog
session actions. The jog session remains independent of the specific input
device.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class InputSource(ABC):
    """Abstract source of actions for an interactive jog session.

    Input sources translate device-specific input, such as keyboard keys or
    gamepad controls, into action names understood by a jog session. The
    session owns the interpretation and execution of those actions, allowing
    different input backends to share the same jogging behavior.

    Subclasses must implement :meth:`run` and remain active until the supplied
    session is no longer running or the input source otherwise terminates.

    Notes:
        Continuous inputs such as held keys, buttons, or analog sticks should
        call ``session.press(action)`` while active and
        ``session.release(action)`` when released. Discrete inputs should call
        ``session.handle(action)`` once.
    """

    @abstractmethod
    def run(self, session) -> None:
        """Process input and dispatch actions to a jog session.

        This method blocks while the input source is active and translates
        device-specific input into calls on ``session``. Continuous movement
        controls should use ``session.press()`` and ``session.release()`` to
        maintain motion while held. One-shot controls should use
        ``session.handle()``.

        Args:
            session: Active jog session that receives translated input
                actions.

        Returns:
            None. The method returns when input processing is complete or the
            jog session has stopped.
        """


class ScriptedInput(InputSource):
    """Dependency-free input source that replays a fixed action sequence.

    Each configured action is dispatched once through ``session.handle()``.
    This makes scripted input suitable for deterministic tests, demonstrations,
    and simple automated jog sequences without requiring a physical input
    device.

    Args:
        actions: Iterable of action names to dispatch, in execution order.

    Attributes:
        actions: Materialized list of action names that will be dispatched
            when :meth:`run` is called.

    Notes:
        Scripted actions are treated as one-shot inputs. Movement actions are
        therefore bounded by the jog session's normal ``handle`` behavior and
        do not require matching ``press``/``release`` calls.
    """

    def __init__(self, actions):
        """Initialize a scripted input sequence.

        Args:
            actions: Iterable of action names to replay.
        """
        self.actions = list(actions)

    def run(self, session) -> None:
        """Replay the configured actions through a jog session.

        Actions are dispatched in their original order. Processing stops
        early if the session is no longer running.

        Args:
            session: Active jog session that receives the scripted actions.

        Returns:
            None.
        """
        for action in self.actions:
            if not session.running:
                break
            session.handle(action)
