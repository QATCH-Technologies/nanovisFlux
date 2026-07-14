from src.hardware.base_connection import BaseConnection
from src.hardware.eth_connection import ETHConnection
from src.hardware.serial_connection import SerialConnection


class Connection:
    """
    Generic connection interface that routes to Ethernet or Serial based on inputs.
    """

    def __init__(
        self, target: str, port_or_baud: int = 115200, timeout: float = 1.0, protocol: str = "auto"
    ) -> None:
        self._strategy: BaseConnection
        if protocol == "auto":
            if "." in target or target.lower() == "localhost":
                protocol = "ethernet"
            else:
                protocol = "serial"

        if protocol == "ethernet":
            tcp_port = 3333 if port_or_baud == 115200 else port_or_baud
            self._strategy = ETHConnection(host=target, port=tcp_port, timeout=timeout)

        elif protocol == "serial":
            self._strategy = SerialConnection(port=target, baudrate=port_or_baud, timeout=timeout)

        else:
            raise ValueError(
                f"Unknown connection protocol: {protocol}. Use 'ethernet', 'serial', or 'auto'."
            )

    def connect(self) -> None:
        self._strategy.connect()

    def disconnect(self) -> None:
        self._strategy.disconnect()

    def send_command(self, command: str, wait_for_ok: bool = True) -> str:
        return self._strategy.send_command(command, wait_for_ok)

    def reset_input_buffer(self) -> None:
        self._strategy.reset_input_buffer()
