"""
src.opentrons_sdk.services.networking

Service interface for network management.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

import os
from typing import Optional

import aiohttp
import models as Models
import paths as Paths
from client import FlexHTTPClient


class NetworkingService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_networking_status(self) -> Models.NetworkingStatus:
        """
        GET /networking/status
        Query the current network connectivity state.
        """
        path = Paths.Endpoints.Networking.STATUS
        data = await self.client.get(path)
        return Models.NetworkingStatus(**data)

    async def get_wifi_list(self, rescan: bool = False) -> Models.WifiNetworks:
        """
        GET /wifi/list
        Scan for visible Wi-Fi networks.

        Args:
            rescan: If True, forces a hardware rescan (can take ~10s).
                    If False, returns cached networks.
        """
        path = Paths.Endpoints.Networking.WIFI_LIST
        params = {"rescan": str(rescan).lower()}
        timeout = 20 if rescan else None
        data = await self.client.get(path, params=params, timeout=timeout)
        return Models.WifiNetworks(**data)

    async def configure_wifi(
        self,
        ssid: str,
        psk: Optional[str] = None,
        security_type: Optional[Models.NetworkingSecurityType] = None,
        hidden: bool = False,
        eap_config: Optional[Models.EapConfigOption] = None,
    ) -> Models.WifiConfigurationResponse:
        """
        POST /wifi/configure
        Configure the wireless network interface.

        Args:
            ssid: The network name.
            psk: The password (pre-shared key).
            security_type: The encryption type (e.g., wpa-psk, wpa-eap).
            hidden: True if the network does not broadcast its SSID.
            eap_config: Configuration for EAP enterprise networks.
        """
        path = Paths.Endpoints.Networking.WIFI_CONFIGURE
        payload = {
            "ssid": ssid,
            "hidden": hidden,
        }
        if psk:
            payload["psk"] = psk

        if security_type:
            payload["securityType"] = security_type

        if eap_config:
            if hasattr(eap_config, "model_dump"):
                payload["eapConfig"] = eap_config.model_dump(exclude_none=True)
            else:
                payload["eapConfig"] = eap_config

        data = await self.client.post(path, json=payload)
        return Models.WifiConfigurationResponse(**data)

    async def get_wifi_keys(self) -> Models.WifiKeyFiles:
        """
        GET /wifi/keys
        Get a list of key files known to the system.
        """
        path = Paths.Endpoints.Networking.WIFI_KEYS
        data = await self.client.get(path)
        return Models.WifiKeyFiles(**data)

    async def add_wifi_key(
        self, file_path: str, filename: Optional[str] = None
    ) -> Models.AddWifiKeyFileResponse:
        """
        POST /wifi/keys
        Upload a new Wi-Fi key file to the robot.

        Args:
            file_path: Local path to the key file (e.g., 'certs/my-cert.pem').
            filename: Optional custom filename to store on the robot.
                      Defaults to the basename of the file_path.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Key file not found: {file_path}")
        path = Paths.Endpoints.Networking.WIFI_KEYS
        final_filename = filename or os.path.basename(file_path)
        form_data = aiohttp.FormData()
        form_data.add_field(
            "key",
            open(file_path, "rb"),
            filename=final_filename,
            content_type="application/octet-stream",
        )
        response = await self.client.post(path, data=form_data)
        return Models.AddWifiKeyFileResponse(**response)

    async def delete_wifi_key(self, key_uuid: str) -> Models.V1BasicResponse:
        """
        DELETE /wifi/keys/{key_uuid}
        Delete a key file from the robot.

        Args:
            key_uuid: The ID of the key to delete (retrieved from get_wifi_keys).
        """
        path = Paths.Endpoints.Networking.WIFI_KEY_DELETE.format(key_uuid=key_uuid)
        data = await self.client.delete(path)
        return Models.V1BasicResponse(**data)

    async def get_eap_options(self) -> Models.EapOptions:
        """
        GET /wifi/eap-options
        Get the supported EAP variants and their configuration parameters.
        """
        path = Paths.Endpoints.Networking.EAP_OPTIONS
        data = await self.client.get(path)
        return Models.EapOptions(**data)

    async def disconnect_wifi(self, ssid: str) -> Models.V1BasicResponse:
        """
        POST /wifi/disconnect
        Deactivates the Wi-Fi connection and removes it from known connections.

        Args:
            ssid: The SSID of the network to disconnect.
        """
        path = Paths.Endpoints.Networking.DISCONNECT
        payload = {"ssid": ssid}
        data = await self.client.post(path, json=payload)
        return Models.V1BasicResponse(**data)
