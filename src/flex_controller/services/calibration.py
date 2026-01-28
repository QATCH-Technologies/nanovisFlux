from typing import Any, Dict, List, Optional

from ..client import FlexHTTPClient
from ..constants import Endpoints
from ..schemas import (
    CutoutFixture,
    DeckConfiguration,
    LabwareOffset,
    LabwareOffsetFilter,
)

# Logging import
try:
    from src.common.log import get_logger

    log = get_logger("FlexCalibration")
except ImportError:
    import logging

    log = logging.getLogger("FlexCalibration")


class CalibrationService:
    """
    Handles Deck Configuration, Labware Offsets, and Instrument Calibrations.
    """

    def __init__(self, client: FlexHTTPClient):
        self.client = client

    # ============================================================================
    #                            DECK CONFIGURATION
    # ============================================================================

    async def get_deck_configuration(self) -> DeckConfiguration:
        """
        GET /deck_configuration
        Get the current physical layout of the Flex deck (Staging areas, Waste chutes).
        """
        data = await self.client.get(Endpoints.DECK_CONFIGURATION)
        return DeckConfiguration(**data["data"])

    async def set_deck_configuration(
        self, fixtures: List[CutoutFixture]
    ) -> DeckConfiguration:
        """
        PUT /deck_configuration
        Inform the robot of its physical setup so it can dodge obstacles.

        Args:
            fixtures: List of CutoutFixture objects defining what is installed where.
        """
        # Convert Pydantic models to list of dicts
        fixtures_data = [f.model_dump(exclude_none=True) for f in fixtures]

        payload = {"data": {"cutoutFixtures": fixtures_data}}

        response = await self.client.put(Endpoints.DECK_CONFIGURATION, json=payload)
        log.info("Flex Deck Configuration updated successfully.")
        return DeckConfiguration(**response["data"])

    # ============================================================================
    #                              LABWARE OFFSETS
    # ============================================================================

    async def add_labware_offset(
        self,
        definition_uri: str,
        location_sequence: List[Dict[str, Any]],
        vector: Dict[str, float],
    ) -> LabwareOffset:
        """
        POST /labwareOffsets
        Store a new labware offset.
        """
        payload = {
            "data": {
                "definitionUri": definition_uri,
                "locationSequence": location_sequence,
                "vector": vector,
            }
        }

        # 201 Created
        response = await self.client.post(Endpoints.LABWARE_OFFSETS, json=payload)
        return LabwareOffset(**response["data"])

    async def get_labware_offsets(
        self, limit: str = "unlimited"
    ) -> List[LabwareOffset]:
        """
        GET /labwareOffsets
        Get all stored offsets.
        """
        params = {"pageLength": limit}
        data = await self.client.get(Endpoints.LABWARE_OFFSETS, params=params)
        return [LabwareOffset(**item) for item in data.get("data", [])]

    async def search_labware_offsets(
        self, filters: List[Dict[str, Any]]
    ) -> List[LabwareOffset]:
        """
        POST /labwareOffsets/searches
        Search for offsets matching specific criteria.
        """
        payload = {"data": {"filters": filters}}

        data = await self.client.post(Endpoints.LABWARE_OFFSETS_SEARCH, json=payload)
        return [LabwareOffset(**item) for item in data.get("data", [])]

    async def delete_labware_offset(self, offset_id: str):
        """
        DELETE /labwareOffsets/{id}
        """
        path = f"{Endpoints.LABWARE_OFFSETS}/{offset_id}"
        await self.client.delete(path)
        log.debug(f"Deleted offset: {offset_id}")

    async def clear_all_offsets(self):
        """
        DELETE /labwareOffsets
        Wipe ALL stored labware offsets from the robot.
        """
        await self.client.delete(Endpoints.LABWARE_OFFSETS)
        log.warning("All labware offsets cleared.")

    # ============================================================================
    #                        PIPETTE OFFSET CALIBRATION
    # ============================================================================

    async def get_pipette_offset_calibrations(
        self, pipette_id: Optional[str] = None, mount: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        GET /calibration/pipette_offset
        """
        params = {}
        if pipette_id:
            params["pipette_id"] = pipette_id
        if mount:
            params["mount"] = mount

        data = await self.client.get(
            Endpoints.CALIBRATION_PIPETTE_OFFSET, params=params
        )
        return data.get("data", [])

    async def delete_pipette_offset_calibration(self, pipette_id: str, mount: str):
        """
        DELETE /calibration/pipette_offset
        """
        params = {"pipette_id": pipette_id, "mount": mount}
        # Client handles 200 OK or errors.
        # API returns 404 if not found, we might want to catch that silently or let it raise.
        # The monolithic script caught 404 silently.
        try:
            await self.client.delete(
                Endpoints.CALIBRATION_PIPETTE_OFFSET, params=params
            )
            log.info(f"Deleted pipette offset calibration for {mount}")
        except Exception as e:
            if "404" in str(e):
                log.warning(
                    f"No offset found to delete for {mount} pipette {pipette_id}"
                )
            else:
                raise e

    # ============================================================================
    #                         TIP LENGTH CALIBRATION
    # ============================================================================

    async def get_tip_length_calibrations(
        self, pipette_id: Optional[str] = None, tiprack_uri: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        GET /calibration/tip_length
        """
        params = {}
        if pipette_id:
            params["pipette_id"] = pipette_id
        if tiprack_uri:
            params["tiprack_uri"] = tiprack_uri

        data = await self.client.get(Endpoints.CALIBRATION_TIP_LENGTH, params=params)
        return data.get("data", [])

    async def delete_tip_length_calibration(self, pipette_id: str, tiprack_uri: str):
        """
        DELETE /calibration/tip_length
        """
        params = {"pipette_id": pipette_id, "tiprack_uri": tiprack_uri}
        try:
            await self.client.delete(Endpoints.CALIBRATION_TIP_LENGTH, params=params)
            log.info(f"Deleted tip length calibration for {tiprack_uri}")
        except Exception as e:
            if "404" in str(e):
                log.warning(
                    f"No tip length calibration found to delete for {pipette_id}"
                )
            else:
                raise e
