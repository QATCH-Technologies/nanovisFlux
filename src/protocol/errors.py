from __future__ import annotations


class ControllerError(Exception):
    """Base for controller-side failures (a 'NOT ok' response)."""

    def __init__(self, message, *, reason=None, response=None):
        super().__init__(message)
        self.reason = reason
        self.response = response


class TransportError(ControllerError):
    """Lost/garbled link, or a timeout waiting for a response."""


class AxisNotHomedError(ControllerError):
    def __init__(self, axis, response=None):
        super().__init__(
            f"axis {axis} not homed", reason=f"axis {axis} not homed", response=response
        )
        self.axis = axis


class EndstopError(ControllerError):
    """Homing failed: no endstop found, or motion aborted mid-home."""


class ProbeError(ControllerError):
    """A probe move (G38.2 / G38.4) did not make/break contact."""


class TooManyAxesError(ControllerError):
    """A probe command named more than one axis."""


def map_error(reason: str | None, response=None) -> ControllerError:
    """Translate a raw 'NOT ok (...)' reason into a typed exception, so
    callers catch AxisNotHomedError instead of string-matching."""
    r = (reason or "").lower()
    if "not homed" in r:
        axis = reason.split("axis", 1)[-1].split("not")[0].strip() if reason else "?"
        return AxisNotHomedError(axis or "?", response)
    if "endstop" in r or "serial pending" in r or "null pointer" in r:
        return EndstopError(reason or "homing failed", reason=reason, response=response)
    if "too many axes" in r:
        return TooManyAxesError(reason or "too many axes", reason=reason, response=response)
    return ControllerError(reason or "command failed", reason=reason, response=response)
