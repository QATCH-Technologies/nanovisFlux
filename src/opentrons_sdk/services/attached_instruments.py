import models as Models
import paths as Paths

try:
    from src.common.log import get_logger

    log = get_logger("AttachedInstrumentsService")
except ImportError:
    import logging

    log = logging.getLogger("AttachedInstrumentsService")


class AttachedInstrumentsService:
    def __init__(self, client):
        self.client = client

    async def get_instruments(
        self,
    ) -> Models.SimpleMultiBodyUnionPipetteGripperBadPipetteBadGripper:
        """
        GET /instruments
        Retrieve a list of all pipettes and grippers attached to the Flex.

        Warning: This is specific to Flex robots. For OT-2, use the
        legacy /pipettes endpoint.
        """
        path = Paths.Endpoints.AttachedInstruments.INSTRUMENTS
        data = await self.client.get(path)
        return Models.SimpleMultiBodyUnionPipetteGripperBadPipetteBadGripper(**data)
