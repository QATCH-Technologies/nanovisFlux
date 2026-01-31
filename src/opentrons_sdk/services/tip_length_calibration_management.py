from typing import Any, Dict, Optional

import models as Models
import paths as Paths

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class TipLengthCalibrationManagementService:
    def __init__(self, client):
        self.client = client

    async def get_tip_lengths(
        self,
        pipette_id: Optional[str] = None,
        tiprack_uri: Optional[str] = None,
        tiprack_hash: Optional[str] = None,
    ) -> Models.DeprecatedMultiResponseModelTipLengthCalibration:
        """
        GET /calibration/tip_length
        Fetch all saved tip length calibrations from the robot.

        Args:
            pipette_id: Filter results by pipette serial number.
            tiprack_uri: Filter by the tip rack's URI (preferred).
            tiprack_hash: Filter by tip rack hash (deprecated).
        """
        path = Paths.Endpoints.TipLengthCalibrationManagement.TIP_LENGTH
        params = {
            "pipette_id": pipette_id,
            "tiprack_uri": tiprack_uri,
            "tiprack_hash": tiprack_hash,
        }

        clean_params = {k: v for k, v in params.items() if v is not None}
        data = await self.client.get(path, params=clean_params)
        return Models.DeprecatedMultiResponseModelTipLengthCalibration(**data)

    async def delete_tip_length(
        self,
        pipette_id: str,
        tiprack_uri: Optional[str] = None,
        tiprack_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        DELETE /calibration/tip_length
        Delete a specific tip length calibration.

        Note: You must provide either tiprack_uri or tiprack_hash.
        URI is preferred for semantically identical definitions.
        """
        path = Paths.Endpoints.TipLengthCalibrationManagement.TIP_LENGTH
        params = {
            "pipette_id": pipette_id,
            "tiprack_uri": tiprack_uri,
            "tiprack_hash": tiprack_hash,
        }
        clean_params = {k: v for k, v in params.items() if v is not None}
        return await self.client.delete(path, params=clean_params)
