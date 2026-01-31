from typing import Any, Dict, Optional

import models as Models
import paths as Paths

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class LabwareCalibrationManagementService:
    def __init__(self, client):
        self.client = client

    async def get_all_labware_calibrations(
        self,
        load_name: Optional[str] = None,
        namespace: Optional[str] = None,
        version: Optional[int] = None,
        parent: Optional[str] = None,
    ) -> Models.DeprecatedMultiResponseModelLabwareCalibration:
        """
        GET /labware/calibrations
        [Deprecated/Removed] Fetch all saved labware calibrations.

        Warning: This endpoint returns 410 Gone on modern robot software.
        Use the /runs endpoints to manage labware offsets instead.
        """
        path = Paths.Endpoints.LabwareCalibrationManagement.LABWARE_CALIBRATIONS
        params = {
            "loadName": load_name,
            "namespace": namespace,
            "version": version,
            "parent": parent,
        }
        clean_params = {k: v for k, v in params.items() if v is not None}
        data = await self.client.get(path, params=clean_params)
        return Models.DeprecatedMultiResponseModelLabwareCalibration(**data)

    async def get_labware_calibration(self, calibration_id: str) -> Dict[str, Any]:
        """
        GET /labware/calibrations/{calibrationId}
        [Deprecated/Removed] Retrieve a specific saved labware calibration by ID.

        Warning: This endpoint returns 410 Gone on modern robot software.
        """
        path = (
            Paths.Endpoints.LabwareCalibrationManagement.LABWARE_CALIBRATION_ID.format(
                calibrationId=calibration_id
            )
        )

        return await self.client.get(path)

    async def delete_labware_calibration(self, calibration_id: str) -> Dict[str, Any]:
        """
        DELETE /labware/calibrations/{calibrationId}
        [Deprecated/Removed] Remove a specific saved labware calibration from the robot.

        Warning: This endpoint returns 410 Gone on modern robot software.
        """
        path = (
            Paths.Endpoints.LabwareCalibrationManagement.LABWARE_CALIBRATION_ID.format(
                calibrationId=calibration_id
            )
        )
        return await self.client.delete(path)
