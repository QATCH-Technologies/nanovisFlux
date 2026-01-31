from typing import Any, Dict, Optional

import models as Models
import paths as Paths

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class OT2CalibrationSessionService:
    def __init__(self, client):
        self.client = client

    async def create_calibration_session(
        self, attributes: Dict[str, Any]
    ) -> (
        Models.RequestModelUnionCalibrationCheckCreateAttributesTipLengthCalibrationCreateAttributesDeckCalibrationCreateAttributesPipetteOffsetCalibrationCreateAttributes
    ):
        """
        POST /sessions
        [Deprecated] Create an OT-2 calibration session.
        """
        path = Paths.Endpoints.OT2CalibrationSessions.SESSIONS_CREATE
        payload = {"data": {"attributes": attributes}}
        data = await self.client.post(path, json=payload)
        return Models.RequestModelUnionCalibrationCheckCreateAttributesTipLengthCalibrationCreateAttributesDeckCalibrationCreateAttributesPipetteOffsetCalibrationCreateAttributes(
            **data
        )

    async def get_all_sessions(
        self, session_type: Optional[str] = None
    ) -> (
        Models.RequestModelUnionCalibrationCheckCreateAttributesTipLengthCalibrationCreateAttributesDeckCalibrationCreateAttributesPipetteOffsetCalibrationCreateAttributes
    ):
        """
        GET /sessions
        [Deprecated] List all active OT-2 calibration sessions.
        """
        path = Paths.Endpoints.OT2CalibrationSessions.SESSIONS_CREATE
        params = {"session_type": session_type} if session_type else {}
        data = await self.client.get(path, params=params)
        return Models.RequestModelUnionCalibrationCheckCreateAttributesTipLengthCalibrationCreateAttributesDeckCalibrationCreateAttributesPipetteOffsetCalibrationCreateAttributes(
            **data
        )

    async def get_session(
        self, session_id: str
    ) -> (
        Models.DeprecatedResponseModelUnionCalibrationCheckResponseAttributesTipLengthCalibrationResponseAttributesDeckCalibrationResponseAttributesPipetteOffsetCalibrationResponseAttributes
    ):
        """
        GET /sessions/{sessionId}
        [Deprecated] Retrieve details for a specific OT-2 calibration session.

        Args:
            session_id: The unique identifier for the calibration session.
        """
        path = Paths.Endpoints.OT2CalibrationSessions.SESSIONS_ID.format(
            sessionId=session_id
        )

        data = await self.client.get(path)

        return Models.DeprecatedResponseModelUnionCalibrationCheckResponseAttributesTipLengthCalibrationResponseAttributesDeckCalibrationResponseAttributesPipetteOffsetCalibrationResponseAttributes(
            **data
        )

    async def delete_session(
        self, session_id: str
    ) -> (
        Models.DeprecatedResponseModelUnionCalibrationCheckResponseAttributesTipLengthCalibrationResponseAttributesDeckCalibrationResponseAttributesPipetteOffsetCalibrationResponseAttributes
    ):
        """
        DELETE /sessions/{sessionId}
        [Deprecated] Terminate and clear a specific calibration session.
        Crucial for freeing up robot resources on the OT-2.
        """
        path = Paths.Endpoints.OT2CalibrationSessions.SESSIONS_ID.format(
            sessionId=session_id
        )

        data = await self.client.delete(path)

        return Models.DeprecatedResponseModelUnionCalibrationCheckResponseAttributesTipLengthCalibrationResponseAttributesDeckCalibrationResponseAttributesPipetteOffsetCalibrationResponseAttributes(
            **data
        )

    async def execute_session_command(
        self,
        session_id: str,
        command_type: str,
        params: Dict[
            str,
            Models.RequestModelUnionSessionCommandRequestLiteralStartRunStartSimulateCancelPauseResumeMoveToTipRackMoveToPointOneMoveToDeckMoveToReferencePointPickUpTipConfirmTipAttachedInvalidateTipSaveOffsetExitInvalidateLastActionMoveToPointTwoMoveToPointThreeComparePointSwitchPipetteReturnTipTransitionEmptyModelEmptyModelSessionCommandRequestLiteralLoadLabwareLoadLabwareCreateLoadLabwareResultSessionCommandRequestLiteralLoadPipetteLoadPipetteCreateLoadPipetteResultSessionCommandRequestLiteralAspirateAspirateCreateAspirateResultSessionCommandRequestLiteralDispenseDispenseCreateDispenseResultSessionCommandRequestLiteralPickUpTipPickUpTipCreatePickUpTipResultSessionCommandRequestLiteralDropTipDropTipCreateDropTipResultSessionCommandRequestLiteralJogJogPositionEmptyModelSessionCommandRequestLiteralSetHasCalibrationBlockSetHasCalibrationBlockRequestDataEmptyModelSessionCommandRequestLiteralLoadLabwareLoadLabwareByDefinitionRequestDataEmptyModel,
        ],
    ) -> (
        Models.DeprecatedResponseModelUnionSessionCommandResponseLiteralStartRunStartSimulateCancelPauseResumeMoveToTipRackMoveToPointOneMoveToDeckMoveToReferencePointPickUpTipConfirmTipAttachedInvalidateTipSaveOffsetExitInvalidateLastActionMoveToPointTwoMoveToPointThreeComparePointSwitchPipetteReturnTipTransitionEmptyModelEmptyModelSessionCommandResponseLiteralLoadLabwareLoadLabwareCreateLoadLabwareResultSessionCommandResponseLiteralLoadPipetteLoadPipetteCreateLoadPipetteResultSessionCommandResponseLiteralAspirateAspirateCreateAspirateResultSessionCommandResponseLiteralDispenseDispenseCreateDispenseResultSessionCommandResponseLiteralPickUpTipPickUpTipCreatePickUpTipResultSessionCommandResponseLiteralDropTipDropTipCreateDropTipResultSessionCommandResponseLiteralJogJogPositionEmptyModelSessionCommandResponseLiteralSetHasCalibrationBlockSetHasCalibrationBlockRequestDataEmptyModelSessionCommandResponseLiteralLoadLabwareLoadLabwareByDefinitionRequestDataEmptyModel
    ):
        """
        POST /sessions/{sessionId}/commands/execute
        [Deprecated] Execute a specific action within an OT-2 calibration session.

        Args:
            session_id: ID of the active calibration session.
            command_type: The literal command string (e.g., 'jog', 'save_offset').
            params: Dictionary of parameters required for the command
                    (e.g., {"vector": [0, 0, 0.1]} for a jog).
        """
        path = Paths.Endpoints.OT2CalibrationSessions.SESSION_COMMAND.format(
            sessionId=session_id
        )
        payload = {"data": {"attributes": {"command": command_type, "data": params}}}
        data = await self.client.post(path, json=payload)
        return Models.DeprecatedResponseModelUnionSessionCommandResponseLiteralStartRunStartSimulateCancelPauseResumeMoveToTipRackMoveToPointOneMoveToDeckMoveToReferencePointPickUpTipConfirmTipAttachedInvalidateTipSaveOffsetExitInvalidateLastActionMoveToPointTwoMoveToPointThreeComparePointSwitchPipetteReturnTipTransitionEmptyModelEmptyModelSessionCommandResponseLiteralLoadLabwareLoadLabwareCreateLoadLabwareResultSessionCommandResponseLiteralLoadPipetteLoadPipetteCreateLoadPipetteResultSessionCommandResponseLiteralAspirateAspirateCreateAspirateResultSessionCommandResponseLiteralDispenseDispenseCreateDispenseResultSessionCommandResponseLiteralPickUpTipPickUpTipCreatePickUpTipResultSessionCommandResponseLiteralDropTipDropTipCreateDropTipResultSessionCommandResponseLiteralJogJogPositionEmptyModelSessionCommandResponseLiteralSetHasCalibrationBlockSetHasCalibrationBlockRequestDataEmptyModelSessionCommandResponseLiteralLoadLabwareLoadLabwareByDefinitionRequestDataEmptyModel(
            **data
        )
