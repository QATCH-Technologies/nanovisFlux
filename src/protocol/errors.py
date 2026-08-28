"""Typed exceptions and error translation for motion-controller failures.

This module defines the exception hierarchy used to represent failures
reported by the motion controller or encountered while communicating with it.
Typed exceptions allow higher-level code to handle specific controller
conditions without parsing raw protocol error strings.

The exception hierarchy is rooted at :class:`ControllerError`, with
specialized subclasses for communication failures, homing failures, probe
failures, and invalid multi-axis probe requests.

The :func:`map_error` helper translates a raw controller failure reason into
the most specific applicable exception type. Unrecognized reasons fall back
to :class:`ControllerError` while preserving the original reason and
controller response for diagnostics.
"""

from __future__ import annotations

from .responses import Response


class ControllerError(Exception):
    """Base exception for failures reported by the motion controller.

    This exception represents a controller-side command failure, typically
    corresponding to a `NOT ok` response. It preserves both a normalized
    message for callers and the underlying controller information for
    diagnostics.

    Attributes:
        reason: Optional raw or controller-provided reason associated with the
            failure.
        response: Optional response object that caused or describes the
            failure.
    """

    def __init__(
        self, message: str, *, reason: str | None = None, response: Response | None = None
    ) -> None:
        """Initialize a controller error.

        Args:
            message: Human-readable error message.
            reason: Optional raw controller error reason.
            response: Optional controller response associated with the error.
        """
        super().__init__(message)
        self.reason = reason
        self.response = response


class TransportError(ControllerError):
    """Exception raised when communication with the controller fails.

    This includes lost or malformed communication links and timeouts while
    waiting for a controller response.
    """


class AxisNotHomedError(ControllerError):
    """Exception raised when an operation requires an unhomed axis.

    Attributes:
        axis: Identifier or description of the axis that has not been homed.
        reason: Controller-provided reason describing the homing failure.
        response: Controller response associated with the failure.
    """

    def __init__(self, axis: str, response: Response | None = None) -> None:
        """Initialize an axis-not-homed error.

        Args:
            axis: Identifier of the axis that has not been homed.
            response: Optional controller response associated with the error.
        """
        super().__init__(
            f"axis {axis} not homed", reason=f"axis {axis} not homed", response=response
        )
        self.axis = axis


class EndstopError(ControllerError):
    """Exception raised when a homing operation fails at an endstop.

    This may indicate that the expected endstop was not detected or that
    homing motion was aborted before the expected endstop condition occurred.
    """


class ProbeError(ControllerError):
    """Exception raised when a probing operation fails to establish contact.

    This represents a failed probing move such as `G38.2` or `G38.4`,
    where the expected contact or contact-release condition was not detected.
    """


class TooManyAxesError(ControllerError):
    """Exception raised when a probe command specifies multiple axes.

    Probe operations supported by the controller require exactly one axis;
    this exception represents a command that violates that constraint.
    """


def map_error(reason: str | None, response: Response | None = None) -> ControllerError:
    """Translate a controller error reason into a typed exception.

    The supplied reason is inspected for known controller failure patterns
    and mapped to the most specific applicable :class:`ControllerError`
    subclass. This allows callers to handle conditions such as an unhomed
    axis or failed endstop without parsing controller-specific error strings.

    Matching is case-insensitive. Unrecognized reasons are represented by a
    generic :class:`ControllerError`.

    Args:
        reason: Raw controller-provided error reason, or `None` when no
            reason was supplied.
        response: Optional controller response associated with the failure.
            The response is preserved on the returned exception.

    Returns:
        ControllerError: A typed exception corresponding to the recognized
        failure reason. Known conditions produce specialized subclasses;
        unrecognized conditions produce a generic :class:`ControllerError`.
    """
    r = (reason or "").lower()
    if "not homed" in r:
        axis = reason.split("axis", 1)[-1].split("not")[0].strip() if reason else "?"
        return AxisNotHomedError(axis or "?", response)
    if "endstop" in r or "serial pending" in r or "null pointer" in r:
        return EndstopError(reason or "homing failed", reason=reason, response=response)
    if "too many axes" in r:
        return TooManyAxesError(reason or "too many axes", reason=reason, response=response)
    return ControllerError(reason or "command failed", reason=reason, response=response)
