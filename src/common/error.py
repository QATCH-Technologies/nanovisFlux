from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from log import get_logger
from pydantic import BaseModel, Field

logger = get_logger("Error")


class ErrorSeverity(str, Enum):
    WARNING = "WARNING"
    RECOVERABLE = "RECOVERABLE"
    CRITICAL = "CRITICAL"


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
    def __init__(
        self,
        message: str,
        code: str = "ERR_GENERIC",
        severity: ErrorSeverity = ErrorSeverity.WARNING,
        source: ErrorSource = ErrorSource.SYSTEM,
        device_id: str = None,
        original_exception: Exception = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.severity = severity
        self.source = source
        self.device_id = device_id
        self.original_exception = original_exception
        logger.error(self.to_schema())

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


if __name__ == "__main__":
    raise SerialError("Test serial error", port="1234")
