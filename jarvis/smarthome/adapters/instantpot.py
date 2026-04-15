"""
Instant Pot / Camp Chef Adapter — BLE-enabled cooking appliances.

Both Instant Pot (newer models) and Camp Chef (pellet grill/smoker) use BLE
to report cooking status and accept mode changes.

Instant Pot BLE:
  - Service UUID: 0000fff0-0000-1000-8000-00805f9b34fb
  - Status characteristic: reports JSON {mode, temp_f, timer_remaining}
  - Command characteristic: accepts JSON {action: "set_mode", value: "..."}

Camp Chef:
  - Similar BLE structure but with probe_temp and grill_temp readings

BLE Matcher:
  - Name contains "Instant Pot" / "IP-" / "Camp Chef" / "CAMPCHEF"
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from jarvis.smarthome.adapters.base import BaseDeviceAdapter
from jarvis.smarthome.models import BaseDevice, CommandResult, DeviceState

logger = logging.getLogger(__name__)

# Instant Pot cook modes
INSTANT_POT_MODES = {
    "pressure_cook", "slow_cook", "saute", "steam", "rice",
    "multigrain", "porridge", "soup", "bean", "poultry",
    "meat_stew", "cake", "egg", "yogurt", "warm", "off",
}

# Camp Chef modes
CAMP_CHEF_MODES = {
    "smoke", "high", "low", "medium", "shutdown", "off",
}


class ApplianceAdapter(BaseDeviceAdapter):
    """
    Adapter for smart cooking appliances (Instant Pot, Camp Chef).
    Reports temperature, cooking mode, and timer status.
    """

    @property
    def adapter_type(self) -> str:
        return "appliance"

    @property
    def supported_commands(self) -> list[str]:
        return ["set_mode", "turn_off", "get_state"]

    def send_command(
        self,
        device: BaseDevice,
        command: str,
        params: Optional[dict[str, Any]] = None,
    ) -> CommandResult:
        params = params or {}

        if command == "turn_off":
            new_state = _copy_state(device.state)
            new_state.power = False
            new_state.mode = "off"
            logger.info("Appliance %s: power off", device.display_name)
            return CommandResult(
                success=True,
                device_id=device.device_id,
                command=command,
                message="powered off",
                new_state=new_state,
            )

        if command == "set_mode":
            mode = str(params.get("value", "")).lower()
            # Validate mode based on manufacturer
            valid_modes = (
                CAMP_CHEF_MODES
                if "camp" in device.manufacturer.lower()
                else INSTANT_POT_MODES
            )
            if mode not in valid_modes:
                return CommandResult(
                    success=False,
                    device_id=device.device_id,
                    command=command,
                    message=f"Invalid mode {mode!r}. Valid: {sorted(valid_modes)}",
                )
            new_state = _copy_state(device.state)
            new_state.power = True
            new_state.mode = mode
            logger.info("Appliance %s: set mode → %s", device.display_name, mode)
            return CommandResult(
                success=True,
                device_id=device.device_id,
                command=command,
                message=f"mode set to {mode}",
                new_state=new_state,
            )

        if command == "get_state":
            return CommandResult(
                success=True,
                device_id=device.device_id,
                command=command,
                message="state polled",
                new_state=device.state,
            )

        return CommandResult(
            success=False,
            device_id=device.device_id,
            command=command,
            message=f"Unknown command: {command!r}",
        )

    def get_state(self, device: BaseDevice) -> DeviceState:
        return device.state

    def can_handle(self, device: BaseDevice) -> bool:
        return device.adapter_type == "appliance"

    @staticmethod
    def ble_matcher(disc: Any) -> Optional[str]:
        name = (disc.name or "").lower()
        if any(k in name for k in ("instant pot", "instapot", "ip-", "camp chef", "campchef")):
            return "appliance"
        return None


def _copy_state(state: DeviceState) -> DeviceState:
    import dataclasses
    return dataclasses.replace(state)
