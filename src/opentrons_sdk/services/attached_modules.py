"""
src.opentrons_sdk.services.attached_modules

Service interface for managing attached modules.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

import models as Models
import paths as Paths
from client import FlexHTTPClient


class AttachedModulesService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_modules(
        self,
    ) -> (
        Models.SimpleMultiBodyUnionTemperatureModuleMagneticModuleThermocyclerModuleHeaterShakerModuleAbsorbanceReaderModuleFlexStackerModule
    ):
        """
        GET /modules
        Retrieve a list of all modules currently attached to the robot via
        USB or internal CAN bus.
        """
        path = Paths.Endpoints.AttachedModules.MODULES_ATTACHED
        data = await self.client.get(path)
        return Models.SimpleMultiBodyUnionTemperatureModuleMagneticModuleThermocyclerModuleHeaterShakerModuleAbsorbanceReaderModuleFlexStackerModule(
            **data
        )
