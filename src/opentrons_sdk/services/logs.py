from typing import Union

import models as Models
import paths as Paths
from client import FlexHTTPClient

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class LogsService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_logs(
        self,
        log_identifier: Union[Models.LogIdentifier, str],
        format: Models.LogFormat,
        records: int = 50000,
    ) -> str:
        """
        GET /logs/{log_identifier}
        Get the robot's troubleshooting logs.

        Args:
            log_identifier: The identifier for the log type (e.g., 'api.log', 'serial.log').
            format: The format of the log output (text or json).
            records: Number of log records to retrieve (max 100,000).
        """
        path = Paths.Endpoints.Logs.LOG_IDENTIFIER.format(log_identifier=log_identifier)
        params = {
            "format": format.value if hasattr(format, "value") else str(format),
            "records": records,
        }
        data = await self.client.get(path, params=params)
        return data