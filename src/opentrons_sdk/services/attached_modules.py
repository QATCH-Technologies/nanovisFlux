import models as Models
import paths as Paths
from client import FlexHTTPClient

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


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
