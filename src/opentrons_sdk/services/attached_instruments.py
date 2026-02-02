"""
src.opentrons_sdk.services.attached_instruments

Service interface for  managing attached instruments.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

import models as Models
import paths as Paths


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
