from typing import Any, Dict, List

import models as Models
import paths as Paths
from client import FlexHTTPClient

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class ErrorRecoverySettingsService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_error_recovery_settings(self) -> Models.SimpleBodyResponseData:
        """
        GET /errorRecovery/settings
        Retrieve the current global error recovery settings for the robot.
        """
        path = Paths.Endpoints.ErrorRecoverySettings.ERROR_RECOVERY
        data = await self.client.get(path)
        return Models.SimpleBodyResponseData(**data)

    async def patch_error_recovery_settings(
        self, enabled: bool
    ) -> Models.SimpleBodyResponseData:
        """
        PATCH /errorRecovery/settings
        Enable or disable error recovery globally.

        Args:
            enabled: Set to True to allow the robot to attempt
                     recovery during command failures.
        """
        path = Paths.Endpoints.ErrorRecoverySettings.ERROR_RECOVERY
        payload = {"data": {"enabled": enabled}}

        data = await self.client.patch(path, json=payload)
        return Models.SimpleBodyResponseData(**data)

    async def reset_error_recovery_settings(self) -> Models.SimpleBodyResponseData:
        """
        DELETE /errorRecovery/settings
        Reset all error recovery settings to their factory defaults.
        """
        path = Paths.Endpoints.ErrorRecoverySettings.ERROR_RECOVERY
        data = await self.client.delete(path)
        return Models.SimpleBodyResponseData(**data)
