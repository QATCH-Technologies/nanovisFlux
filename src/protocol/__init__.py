"""Public interface for low-level motion-controller communication.

This package exposes the command, controller, and response types used to
communicate with and control the underlying motion hardware. It provides
structured representations of controller commands rather than requiring
callers to construct protocol messages directly.

The public API includes:

* :class:`Controller` -- Interface for sending commands to the motion
  controller and receiving responses.
* :class:`Command` and its concrete subclasses -- Structured motion,
  homing, probing, configuration, and controller-management commands.
* :class:`Response` and :class:`ProbeResult` -- Structured representations of
  controller responses.
* :mod:`errors` -- Controller-specific exceptions and error definitions.

The names listed in `__all__` form the intended public interface of this
package. Internal implementation details of the command, driver, and response
modules should generally be accessed through these exported types instead.
"""

from . import errors
from .commands import (
    Command,
    DisableLimits,
    EmergencyStop,
    Home,
    LinearMove,
    Probe,
    ProbeMode,
    QuickStop,
    RapidMove,
    ReportPosition,
    Reset,
    SetAbsolute,
    SetAccelerations,
    SetHardLimits,
    SetHomingRetract,
    SetHomingSpeeds,
    SetRelative,
    SetTravelSpeeds,
)
from .driver import Controller
from .responses import ProbeResult, Response

__all__ = [
    "Command",
    "Controller",
    "DisableLimits",
    "EmergencyStop",
    "Home",
    "LinearMove",
    "Probe",
    "ProbeMode",
    "ProbeResult",
    "QuickStop",
    "RapidMove",
    "ReportPosition",
    "Reset",
    "Response",
    "SetAbsolute",
    "SetAccelerations",
    "SetHardLimits",
    "SetHomingRetract",
    "SetHomingSpeeds",
    "SetRelative",
    "SetTravelSpeeds",
    "errors",
]
