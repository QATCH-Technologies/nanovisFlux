from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from log import get_logger
from pydantic import BaseModel, Field

logger = get_logger("Error")


class ErrorSeverity(str, Enum):
    WARNING = "WARNING"  # Information/Minor issue (e.g., 404 Not Found)
    RECOVERABLE = "RECOVERABLE"  # Can retry or wait (e.g., 409 Conflict, 503 Busy)
    CRITICAL = "CRITICAL"  # Stop everything (e.g., Connection Refused)


class ErrorSource(str, Enum):
    SYSTEM = "SYSTEM"
    SERIAL = "SERIAL"
    FLEX = "FLEX"
    ML = "ML"
    NETWORK = "NETWORK"
    PORT_SELECTOR = "PORT_SELECTOR"
    HUMIDITY_CONTROLLER = "HUMIDITY_CONTROLLER"
    SENSOR_ARRAY = "SENSOR_ARRAY"


class AbstractError(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    error_code: str
    message: str
    source: ErrorSource
    severity: ErrorSeverity
    device_id: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class FluxException(Exception):
    """Base Exception for the entire application."""

    def __init__(
        self,
        message: str,
        code: str = "ERR_GENERIC",
        severity: ErrorSeverity = ErrorSeverity.WARNING,
        source: ErrorSource = ErrorSource.SYSTEM,
        device_id: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.severity = severity
        self.source = source
        self.device_id = device_id
        self.original_exception = original_exception

        # Auto-log on creation
        logger.error(f"[{self.code}] {self.message}")

    def to_schema(self) -> AbstractError:
        return AbstractError(
            error_code=self.code,
            message=self.message,
            source=self.source,
            severity=self.severity,
            device_id=self.device_id,
            meta=(
                {"original_error": str(self.original_exception)}
                if self.original_exception
                else {}
            ),
        )


class SerialError(FluxException):
    def __init__(self, message: str, port: str):
        super().__init__(
            message=message,
            code="ERR_SERIAL",
            severity=ErrorSeverity.CRITICAL,
            source=ErrorSource.SERIAL,
            device_id=port,
        )


# --- Opentrons Flex Specific Errors ---


class FlexBaseError(FluxException):
    """Base class for all Flex errors to ensure correct Source."""

    def __init__(self, message: str, code: str, severity: ErrorSeverity):
        super().__init__(
            message=message, code=code, severity=severity, source=ErrorSource.FLEX
        )


class FlexConnectionError(FlexBaseError):
    """Raised when the robot cannot be reached (Network/Timeout)."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="ERR_FLEX_CONN",
            severity=ErrorSeverity.CRITICAL,  # Stop run immediately
        )


class FlexMaintenanceError(FlexBaseError):
    """Raised when robot is reachable but booting or updating (HTTP 503)."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="ERR_FLEX_MAINT",
            severity=ErrorSeverity.RECOVERABLE,  # Wait and retry
        )


class FlexConflictError(FlexBaseError):
    """Raised when a command conflicts with current robot state (HTTP 409)."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            code="ERR_FLEX_CONFLICT",
            severity=ErrorSeverity.RECOVERABLE,  # Logic error, but robot is fine
        )


class FlexNotFoundError(FlexBaseError):
    """Raised when a resource (run, labware, protocol) is missing (HTTP 404)."""

    def __init__(self, message: str):
        super().__init__(
            message=message, code="ERR_FLEX_NOT_FOUND", severity=ErrorSeverity.WARNING
        )


class FlexCommandError(FlexBaseError):
    """Generic fallback for other 4xx/5xx API errors."""

    def __init__(self, message: str):
        super().__init__(
            message=message, code="ERR_FLEX_CMD", severity=ErrorSeverity.CRITICAL
        )


if __name__ == "__main__":
    raise FlexCommandError("Test Error")
