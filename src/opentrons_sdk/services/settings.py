"""
src.opentrons_sdk.services.settings

Service interface for general Opentrons settings.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

from typing import Any, Dict, Union

import models as Models
import paths as Paths
from client import FlexHTTPClient


class SettingsService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_settings(self) -> Models.AdvancedSettingsResponse:
        """
        GET /settings
        Get a list of available advanced settings (feature flags) and their values.
        """
        path = Paths.Endpoints.SystemSettings.SETTINGS_GET
        data = await self.client.get(path)
        return Models.AdvancedSettingsResponse(**data)

    async def update_setting(
        self, setting: Union[Models.AdvancedSettingRequest, Dict[str, Any]]
    ) -> Models.AdvancedSettingsResponse:
        """
        POST /settings
        Change an advanced setting (feature flag).

        Args:
            setting: An AdvancedSettingRequest model or dict containing the setting ID and new value.
        """
        path = Paths.Endpoints.SystemSettings.SETTINGS_CHANGE
        if isinstance(setting, Models.AdvancedSettingRequest):
            payload = setting.model_dump(exclude_none=True)
        else:
            payload = dict(setting)
        data = await self.client.post(path, json=payload)
        return Models.AdvancedSettingsResponse(**data)

    async def set_local_log_level(
        self, log_level: Union[Models.LogLevel, Dict[str, Any]]
    ) -> Models.V1BasicResponse:
        """
        POST /settings/log_level/local
        Set the minimum level of logs saved locally on the robot.

        Args:
            log_level: A LogLevel model or dict (e.g., {"log_level": "debug"}).
        """
        path = Paths.Endpoints.SystemSettings.LOG_LEVEL_LOCAL
        if isinstance(log_level, Models.LogLevel):
            payload = log_level.model_dump(exclude_none=True)
        else:
            payload = dict(log_level)
        data = await self.client.post(path, json=payload)
        return Models.V1BasicResponse(**data)

    async def set_upstream_log_level(
        self, log_level: Union[Models.LogLevel, Dict[str, Any]]
    ) -> Models.V1BasicResponse:
        """
        POST /settings/log_level/upstream
        Set the minimum level of logs sent upstream to Opentrons.

        WARNING: Deprecated. This was removed in robot software v7.2.0.

        Args:
            log_level: A LogLevel model or dict (e.g., {"log_level": "info"}).
        """
        path = Paths.Endpoints.SystemSettings.LOG_LEVEL_UPSTREAM
        if isinstance(log_level, Models.LogLevel):
            payload = log_level.model_dump(exclude_none=True)
        else:
            payload = dict(log_level)

        data = await self.client.post(path, json=payload)
        return Models.V1BasicResponse(**data)

    async def get_reset_options(self) -> Models.FactoryResetOptions:
        """
        GET /settings/reset/options
        Get the robot settings and data that can be reset.
        """
        path = Paths.Endpoints.SystemSettings.RESET_OPTIONS
        data = await self.client.get(path)
        return Models.FactoryResetOptions(**data)

    async def reset_settings(self, options: Dict[str, bool]) -> Models.V1BasicResponse:
        """
        POST /settings/reset
        Perform a reset of the requested robot settings or data.

        Note: You should always restart the robot after using this endpoint.
        Valid keys for the options dictionary can be retrieved via get_reset_options().

        Args:
            options: A dictionary mapping reset category names to boolean toggle.
                     Example: {"deckCalibration": True, "networking": True}
        """
        path = Paths.Endpoints.SystemSettings.RESET
        data = await self.client.post(path, json=options)
        return Models.V1BasicResponse(**data)

    async def get_robot_settings(self) -> Dict[str, Any]:
        """
        GET /settings/robot
        Get the current robot config.
        """
        path = Paths.Endpoints.SystemSettings.ROBOT_SETTINGS
        data = await self.client.get(path)
        return data

    async def get_all_pipette_settings(self) -> Dict[str, Models.PipetteSettings]:
        """
        GET /settings/pipettes
        List all settings for all known pipettes by id.

        Note: Per the API spec, this is primarily available for OT-2.
        """
        path = Paths.Endpoints.Components.PIPETTE_SETTINGS
        data = await self.client.get(path)
        return {
            pipette_id: Models.PipetteSettings(**settings)
            for pipette_id, settings in data.items()
        }

    async def get_pipette_settings(self, pipette_id: str) -> Models.PipetteSettings:
        """
        GET /settings/pipettes/{pipette_id}
        Get the settings of a specific pipette by ID.

        Note: Per the API spec, this is primarily available for OT-2.
        """
        path = Paths.Endpoints.Components.PIPETTE_ID_SETTING.format(
            pipette_id=pipette_id
        )
        data = await self.client.get(path)
        return Models.PipetteSettings(**data)

    async def update_pipette_settings(
        self,
        pipette_id: str,
        settings_update: Union[Models.PipetteSettingsUpdate, Dict[str, Any]],
    ) -> Models.PipetteSettings:
        """
        PATCH /settings/pipettes/{pipette_id}
        Change the settings of a specific pipette.

        Note: Per the API spec, this is primarily available for OT-2.

        Args:
            pipette_id: The unique ID of the pipette to update.
            settings_update: A PipetteSettingsUpdate model or dict containing the fields to change.
        """
        path = Paths.Endpoints.Components.PIPETTE_ID_SETTING.format(
            pipette_id=pipette_id
        )
        if isinstance(settings_update, Models.PipetteSettingsUpdate):
            payload = settings_update.model_dump(exclude_none=True)
        else:
            payload = dict(settings_update)
        data = await self.client.patch(path, json=payload)
        return Models.PipetteSettings(**data)
