"""
Generic Adapter — handles any MQTT or HTTP device that follows Jarvis conventions.

MQTT convention:
  <prefix>/state   → device publishes JSON state updates
  <prefix>/cmd     → Jarvis publishes commands

HTTP convention:
  GET  <base_url>/state         → returns JSON state
  POST <base_url>/command       → {"command": "...", "params": {...}}

The device record's metadata["mqtt_prefix"] or metadata["http_base"] tells
the adapter where to reach the device.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from jarvis.smarthome.adapters.base import BaseDeviceAdapter
from jarvis.smarthome.models import BaseDevice, CommandResult, DeviceState, Protocol

logger = logging.getLogger(__name__)


class GenericMQTTAdapter(BaseDeviceAdapter):
    """
    Generic MQTT adapter. Publishes structured command messages and
    subscribes to state topic for updates.
    """

    def __init__(self, mqtt_client: Any = None) -> None:
        self._mqtt = mqtt_client  # MQTTClient or None

    @property
    def adapter_type(self) -> str:
        return "generic_mqtt"

    @property
    def supported_commands(self) -> list[str]:
        return [
            "turn_on", "turn_off", "set_brightness", "set_color_temp",
            "set_volume", "set_mode", "set_temperature", "lock", "unlock",
        ]

    def send_command(
        self,
        device: BaseDevice,
        command: str,
        params: Optional[dict[str, Any]] = None,
    ) -> CommandResult:
        params = params or {}
        prefix = device.metadata.get("mqtt_prefix", f"jarvis/{device.device_id}")

        if self._mqtt is None:
            logger.warning("No MQTT client — state update only for %s", device.display_name)
            new_state = self._apply_command_to_state(device.state, command, params)
            return CommandResult(
                success=True,
                device_id=device.device_id,
                command=command,
                message="no mqtt client; state updated locally",
                new_state=new_state,
            )

        payload = {"command": command, "params": params}
        sent = self._mqtt.publish(f"{prefix}/cmd", payload)
        new_state = self._apply_command_to_state(device.state, command, params)
        return CommandResult(
            success=sent,
            device_id=device.device_id,
            command=command,
            message="published" if sent else "mqtt publish failed",
            new_state=new_state,
        )

    def get_state(self, device: BaseDevice) -> DeviceState:
        return device.state

    def on_state_update(self, device: BaseDevice, raw: dict[str, Any]) -> DeviceState:
        """Parse inbound MQTT state message."""
        state = _copy_state(device.state)
        if "power" in raw:
            state.power = bool(raw["power"])
        if "brightness" in raw:
            state.brightness = int(raw["brightness"])
        if "color_temp" in raw:
            state.color_temp = int(raw["color_temp"])
        if "temperature_f" in raw:
            state.temperature_f = float(raw["temperature_f"])
        if "target_temp_f" in raw:
            state.target_temp_f = float(raw["target_temp_f"])
        if "mode" in raw:
            state.mode = str(raw["mode"])
        if "volume" in raw:
            state.volume = int(raw["volume"])
        return state

    def can_handle(self, device: BaseDevice) -> bool:
        return device.adapter_type == "generic_mqtt" or (
            device.protocol == Protocol.MQTT and device.adapter_type == "generic"
        )

    @staticmethod
    def _apply_command_to_state(
        state: DeviceState, command: str, params: dict[str, Any]
    ) -> DeviceState:
        new = _copy_state(state)
        if command == "turn_on":
            new.power = True
        elif command == "turn_off":
            new.power = False
        elif command == "set_brightness":
            new.brightness = max(0, min(100, int(params.get("value", 100))))
        elif command == "set_color_temp":
            new.color_temp = int(params.get("value", 3000))
        elif command == "set_volume":
            new.volume = max(0, min(100, int(params.get("value", 50))))
        elif command == "set_mode":
            new.mode = str(params.get("value", ""))
        elif command == "set_temperature":
            new.target_temp_f = float(params.get("value", 70))
        elif command == "lock":
            new.lock_state = "locked"
        elif command == "unlock":
            new.lock_state = "unlocked"
        return new


class GenericHTTPAdapter(BaseDeviceAdapter):
    """Generic HTTP/REST adapter for LAN-reachable devices."""

    @property
    def adapter_type(self) -> str:
        return "generic_http"

    @property
    def supported_commands(self) -> list[str]:
        return ["turn_on", "turn_off", "set_brightness", "set_mode"]

    def send_command(
        self,
        device: BaseDevice,
        command: str,
        params: Optional[dict[str, Any]] = None,
    ) -> CommandResult:
        params = params or {}
        base_url = device.metadata.get("http_base", f"http://{device.address}")

        try:
            import requests
            resp = requests.post(
                f"{base_url}/command",
                json={"command": command, "params": params},
                timeout=5,
            )
            success = resp.status_code < 300
            new_state = GenericMQTTAdapter._apply_command_to_state(device.state, command, params)
            return CommandResult(
                success=success,
                device_id=device.device_id,
                command=command,
                message=resp.text[:200] if not success else "OK",
                new_state=new_state if success else None,
            )
        except Exception as exc:
            logger.error("HTTP command error for %s: %s", device.display_name, exc)
            return CommandResult(
                success=False,
                device_id=device.device_id,
                command=command,
                message=str(exc),
            )

    def get_state(self, device: BaseDevice) -> DeviceState:
        base_url = device.metadata.get("http_base", f"http://{device.address}")
        try:
            import requests
            resp = requests.get(f"{base_url}/state", timeout=5)
            if resp.status_code < 300:
                return GenericMQTTAdapter().on_state_update(device, resp.json())
        except Exception as exc:
            logger.error("HTTP get_state error for %s: %s", device.display_name, exc)
        return device.state

    def can_handle(self, device: BaseDevice) -> bool:
        return device.adapter_type == "generic_http" or (
            device.protocol == Protocol.HTTP and device.adapter_type == "generic"
        )


def _copy_state(state: DeviceState) -> DeviceState:
    import dataclasses
    return dataclasses.replace(state)
