"""
BaseDeviceAdapter — abstract interface every device adapter must implement.

Each adapter handles one brand/protocol family (HubSpace, Instant Pot, etc.)
and knows how to:
  1. Translate high-level commands ("turn_on", "set_brightness") into
     protocol-level calls (BLE GATT write, MQTT publish, HTTP POST, …)
  2. Parse state updates back into a DeviceState
  3. Report which devices it can handle (via a BLE matcher or HTTP probe)

Adapters operate on a BaseDevice record and return CommandResult.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from jarvis.smarthome.models import BaseDevice, CommandResult, DeviceState


class BaseDeviceAdapter(ABC):
    """Abstract base for all device adapters."""

    # ── Identity ──────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """Short string identifier, e.g. 'hubspace', 'instantpot', 'generic'."""

    @property
    def supported_commands(self) -> list[str]:
        """List of command names this adapter understands."""
        return []

    # ── Core interface ────────────────────────────────────────────────────────

    @abstractmethod
    def send_command(
        self,
        device: BaseDevice,
        command: str,
        params: Optional[dict[str, Any]] = None,
    ) -> CommandResult:
        """
        Execute a command on the device.

        Common commands (adapters implement what they support):
          turn_on / turn_off
          set_brightness <0-100>
          set_color_temp <kelvin>
          set_color_rgb <r,g,b>
          set_volume <0-100>
          set_mode <mode_str>
          set_temperature <fahrenheit>
          lock / unlock
        """

    @abstractmethod
    def get_state(self, device: BaseDevice) -> DeviceState:
        """Poll the device and return its current state."""

    # ── Optional hooks ────────────────────────────────────────────────────────

    def on_state_update(self, device: BaseDevice, raw: dict[str, Any]) -> DeviceState:
        """
        Parse an inbound state update (e.g. MQTT message) into a DeviceState.
        Override for push-based devices.
        """
        return device.state

    def can_handle(self, device: BaseDevice) -> bool:
        """Return True if this adapter can manage the given device."""
        return device.adapter_type == self.adapter_type


class MockAdapter(BaseDeviceAdapter):
    """
    In-memory adapter for testing and simulation.
    Accepts any command, updates an internal state dict.
    """

    def __init__(self) -> None:
        self._states: dict[str, DeviceState] = {}

    @property
    def adapter_type(self) -> str:
        return "mock"

    @property
    def supported_commands(self) -> list[str]:
        return [
            "turn_on", "turn_off", "set_brightness", "set_color_temp",
            "set_color_rgb", "set_volume", "set_mode", "set_temperature",
            "lock", "unlock",
        ]

    def send_command(
        self,
        device: BaseDevice,
        command: str,
        params: Optional[dict[str, Any]] = None,
    ) -> CommandResult:
        params = params or {}
        state = self._states.get(device.device_id) or DeviceState()

        if command == "turn_on":
            state.power = True
        elif command == "turn_off":
            state.power = False
        elif command == "set_brightness":
            state.brightness = max(0, min(100, int(params.get("value", 100))))
        elif command == "set_color_temp":
            state.color_temp = int(params.get("value", 3000))
        elif command == "set_color_rgb":
            r = params.get("r", 255)
            g = params.get("g", 255)
            b = params.get("b", 255)
            state.color_rgb = (int(r), int(g), int(b))
        elif command == "set_volume":
            state.volume = max(0, min(100, int(params.get("value", 50))))
        elif command == "set_mode":
            state.mode = str(params.get("value", ""))
        elif command == "set_temperature":
            state.target_temp_f = float(params.get("value", 70))
        elif command == "lock":
            state.lock_state = "locked"
        elif command == "unlock":
            state.lock_state = "unlocked"
        else:
            return CommandResult(
                success=False,
                device_id=device.device_id,
                command=command,
                message=f"Unknown command: {command!r}",
            )

        self._states[device.device_id] = state
        return CommandResult(
            success=True,
            device_id=device.device_id,
            command=command,
            message=f"OK",
            new_state=state,
        )

    def get_state(self, device: BaseDevice) -> DeviceState:
        return self._states.get(device.device_id) or DeviceState()

    def can_handle(self, device: BaseDevice) -> bool:
        return True   # mock handles everything
