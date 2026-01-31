from typing import Any, Dict, Optional

import models as Models
import paths as Paths

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class PipetteOffsetCalibrationManagementService:
    def __init__(self, client):
        self.client = client

    async def get_pipette_offsets(
        self, pipette_id: Optional[str] = None, mount: Optional[str] = None
    ) -> Models.DeprecatedMultiResponseModelPipetteOffsetCalibration:
        """
        GET /calibration/pipette_offset
        Fetch all saved pipette offset calibrations.

        Args:
            pipette_id: Filter by pipette serial number.
            mount: Filter by 'left' or 'right' mount.
        """
        path = Paths.Endpoints.PipetteOffsetCalibrationManagement.PIPETTE_OFFSET
        params = {"pipette_id": pipette_id, "mount": mount}
        clean_params = {k: v for k, v in params.items() if v is not None}
        data = await self.client.get(path, params=clean_params)
        return Models.DeprecatedMultiResponseModelPipetteOffsetCalibration(**data)

    async def delete_pipette_offset(
        self,
        pipette_id: str,
        mount: Models.RobotServerServicePipetteOffsetModelsMountType,
    ) -> Dict:
        """
        DELETE /calibration/pipette_offset
        Delete a specific pipette calibration by serial and mount.

        Args:
            pipette_id: The serial number of the pipette.
            mount: 'left' or 'right'.
        """
        path = Paths.Endpoints.PipetteOffsetCalibrationManagement.PIPETTE_OFFSET
        params = {"pipette_id": pipette_id, "mount": mount}
        return await self.client.delete(path, params=params)
