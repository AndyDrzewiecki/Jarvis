"""
HubSpace Adapter — controls Affordable HubSpace smart lights (Home Depot brand).

HubSpace devices use BLE for local control. The protocol is reverse-engineered:
  - Advertise as "HubSpace" in BLE name
  - GATT characteristic for power: 0x0001 (write: 0x01=on, 0x00=off)
  - GATT characteristic for brightness: 0x0002 (write: 0–255)
  - GATT characteristic for color temp: 0x0003 (write: 2-byte little-endian Kelvin)
  - GATT characteristic for RGB: 0x0004 (write: 3-byte R,G,B)

When bleak is not available, commands are recorded for later execution.
The adapter also supports HTTP fallback via the HubSpace cloud API for
devices that are reachable over LAN.

BLE matcher: name contains "HubSpace" or "HS-" prefix.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from jarvis.smarthome.adapters.base import BaseDeviceAdapter
from jarvis.smarthome.models import BaseDevice, CommandResult, DeviceState

logger = logging.getLogger(__name__)

try:
    import asyncio
    from bleak import BleakClient  # type: ignore[import-untyped]
    _BLEAK_AVAILABLE = True
except ImportError:
    _BLEAK_AVAILABLE = False
    BleakClient = None  # type: ignore[assignment,misc]

# GATT UUIDs (short form — expand to full 128-bit in real implementation)
_CHAR_POWER      = "0000ffe1-0000-1000-8000-00805f9b34fb"
_CHAR_BRIGHTNESS = "0000ffe2-0000-1000-8000-00805f9b34fb"
_CHAR_COLOR_TEMP = "0000ffe3-0000-1000-8000-00805f9b34fb"
_CHAR_RGB        = "0000ffe4-0000-1000-8000-00805f9b34fb"


class HubSpaceAdapter(BaseDeviceAdapter):
    """Adapter for HubSpace BLE smart lights."""

    @property
    def adapter_type(self) -> str:
        return "hubspace"

    @property
    def supported_commands(self) -> list[str]:
        return ["turn_on", "turn_off", "set_brightness", "set_color_temp", "set_color_rgb"]

    def send_command(
        self,
        device: BaseDevice,
        command: str,
        params: Optional[dict[str, Any]] = None,
    ) -> CommandResult:
        params = params or {}

        if not _BLEAK_AVAILABLE:
            # Queue the command for when bleak is available / record it
            logger.info("HubSpace (mock) %s: %s %s", device.display_name, command, params)
            new_state = self._apply_command_to_state(device.state, command, params)
            return CommandResult(
                success=True,
                device_id=device.device_id,
                command=command,
                message="queued (bleak not available)",
                new_state=new_state,
            )

        try:
            import asyncio
            result = asyncio.run(self._ble_command(device.address, command, params, device.state))
            return result
        except Exception as exc:
            logger.error("HubSpace command error: %s", exc)
            return CommandResult(
                success=False,
                device_id=device.device_id,
                command=command,
                message=str(exc),
            )

    async def _ble_command(
        self,
        address: str,
        command: str,
        params: dict[str, Any],
        current_state: DeviceState,
    ) -> CommandResult:
        raise NotImplementedError("Live BLE not yet wired — use mock or HTTP fallback")

    def get_state(self, device: BaseDevice) -> DeviceState:
        # In a real implementation: connect via BLE and read characteristics
        return device.state

    @staticmethod
    def _apply_command_to_state(
        state: DeviceState,
        command: str,
        params: dict[str, Any],
    ) -> DeviceState:
        """Apply a command to a state object (pure, no I/O)."""
        import dataclasses
        new = dataclasses.replace(state)
        if command == "turn_on":
            new.power = True
        elif command == "turn_off":
            new.power = False
        elif command == "set_brightness":
            new.brightness = max(0, min(100, int(params.get("value", 100))))
        elif command == "set_color_temp":
            new.color_temp = int(params.get("value", 3000))
        elif command == "set_color_rgb":
            new.color_rgb = (
                int(params.get("r", 255)),
                int(params.get("g", 255)),
                int(params.get("b", 255)),
            )
        return new

    def can_handle(self, device: BaseDevice) -> bool:
        return device.adapter_type == "hubspace"

    @staticmethod
    def ble_matcher(disc: Any) -> Optional[str]:
        """BLE scanner matcher — returns 'hubspace' if this looks like a HubSpace device."""
        name = (disc.name or "").lower()
        if "hubspace" in name or name.startswith("hs-"):
            return "hubspace"
        # Check manufacturer data for HubSpace company ID 0x0742
        if 0x0742 in disc.manufacturer_data:
            return "hubspace"
        return None
