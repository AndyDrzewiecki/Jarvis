"""
TV Adapter — controls televisions via CEC (HDMI), IR (infrared), or BLE.

HDMI-CEC allows control of any HDMI-connected TV through the cec-client
command-line tool (part of libcec). IR uses a serial/USB blaster.
Newer smart TVs (LG, Samsung, Sony) also support BLE remote.

Supported commands:
  turn_on / turn_off
  set_volume <0-100>
  set_input <hdmi1, hdmi2, …>
  mute / unmute
  channel_up / channel_down

BLE matcher: name contains "TV", "LG", "Samsung", "BRAVIA", "TCL"
"""
from __future__ import annotations

import logging
import subprocess
from typing import Any, Optional

from jarvis.smarthome.adapters.base import BaseDeviceAdapter
from jarvis.smarthome.models import BaseDevice, CommandResult, DeviceState, Protocol

logger = logging.getLogger(__name__)


class TVAdapter(BaseDeviceAdapter):
    """Controls TVs via CEC, IR, or BLE depending on device protocol."""

    @property
    def adapter_type(self) -> str:
        return "tv"

    @property
    def supported_commands(self) -> list[str]:
        return [
            "turn_on", "turn_off", "set_volume", "mute", "unmute",
            "set_input", "channel_up", "channel_down",
        ]

    def send_command(
        self,
        device: BaseDevice,
        command: str,
        params: Optional[dict[str, Any]] = None,
    ) -> CommandResult:
        params = params or {}

        if device.protocol == Protocol.CEC:
            return self._cec_command(device, command, params)
        elif device.protocol == Protocol.IR:
            return self._ir_command(device, command, params)
        else:
            # BLE / HTTP — fall back to state-only simulation
            return self._simulated_command(device, command, params)

    # ── CEC ───────────────────────────────────────────────────────────────────

    def _cec_command(
        self, device: BaseDevice, command: str, params: dict[str, Any]
    ) -> CommandResult:
        """Send CEC command via cec-client subprocess."""
        cec_cmd = self._to_cec(command, params)
        if cec_cmd is None:
            return CommandResult(
                success=False,
                device_id=device.device_id,
                command=command,
                message=f"No CEC mapping for {command!r}",
            )
        try:
            result = subprocess.run(
                ["cec-client", "-s", "-d", "1"],
                input=cec_cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            success = result.returncode == 0
            new_state = self._apply_command_to_state(device.state, command, params)
            return CommandResult(
                success=success,
                device_id=device.device_id,
                command=command,
                message=result.stdout.strip() or result.stderr.strip(),
                new_state=new_state if success else None,
            )
        except FileNotFoundError:
            logger.warning("cec-client not found — recording state only")
            new_state = self._apply_command_to_state(device.state, command, params)
            return CommandResult(
                success=True,
                device_id=device.device_id,
                command=command,
                message="cec-client not installed; state updated locally",
                new_state=new_state,
            )
        except Exception as exc:
            return CommandResult(
                success=False,
                device_id=device.device_id,
                command=command,
                message=str(exc),
            )

    @staticmethod
    def _to_cec(command: str, params: dict[str, Any]) -> Optional[str]:
        mapping = {
            "turn_on":  "on 0\n",
            "turn_off": "standby 0\n",
            "mute":     "as\n",          # active source / audio mute
            "unmute":   "as\n",
        }
        if command == "set_volume":
            vol = int(params.get("value", 50))
            # CEC volume is relative; we send vol-up/down sequences
            # For simplicity, send a single "volup" or "voldown"
            return "volup\n" if vol > 50 else "voldown\n"
        return mapping.get(command)

    # ── IR ────────────────────────────────────────────────────────────────────

    def _ir_command(
        self, device: BaseDevice, command: str, params: dict[str, Any]
    ) -> CommandResult:
        """Send IR command. Requires LIRC or similar IR blaster daemon."""
        ir_remote = device.metadata.get("ir_remote", "unknown_tv")
        ir_key = self._to_ir_key(command, params)
        if ir_key is None:
            return CommandResult(
                success=False,
                device_id=device.device_id,
                command=command,
                message=f"No IR mapping for {command!r}",
            )
        try:
            result = subprocess.run(
                ["irsend", "SEND_ONCE", ir_remote, ir_key],
                capture_output=True,
                text=True,
                timeout=5,
            )
            success = result.returncode == 0
            new_state = self._apply_command_to_state(device.state, command, params) if success else None
            return CommandResult(
                success=success,
                device_id=device.device_id,
                command=command,
                message=result.stderr.strip() if not success else "OK",
                new_state=new_state,
            )
        except FileNotFoundError:
            logger.warning("irsend not found — recording state only")
            new_state = self._apply_command_to_state(device.state, command, params)
            return CommandResult(
                success=True,
                device_id=device.device_id,
                command=command,
                message="irsend not installed; state updated locally",
                new_state=new_state,
            )
        except Exception as exc:
            return CommandResult(
                success=False,
                device_id=device.device_id,
                command=command,
                message=str(exc),
            )

    @staticmethod
    def _to_ir_key(command: str, params: dict[str, Any]) -> Optional[str]:
        mapping = {
            "turn_on": "KEY_POWER",
            "turn_off": "KEY_POWER",
            "mute": "KEY_MUTE",
            "unmute": "KEY_MUTE",
            "volume_up": "KEY_VOLUMEUP",
            "volume_down": "KEY_VOLUMEDOWN",
            "channel_up": "KEY_CHANNELUP",
            "channel_down": "KEY_CHANNELDOWN",
        }
        if command == "set_volume":
            val = int(params.get("value", 50))
            return "KEY_VOLUMEUP" if val > 50 else "KEY_VOLUMEDOWN"
        return mapping.get(command)

    # ── Simulated (BLE/HTTP/unknown) ──────────────────────────────────────────

    def _simulated_command(
        self, device: BaseDevice, command: str, params: dict[str, Any]
    ) -> CommandResult:
        if command not in self.supported_commands:
            return CommandResult(
                success=False,
                device_id=device.device_id,
                command=command,
                message=f"Unknown command: {command!r}",
            )
        new_state = self._apply_command_to_state(device.state, command, params)
        return CommandResult(
            success=True,
            device_id=device.device_id,
            command=command,
            message="state updated (simulated)",
            new_state=new_state,
        )

    @staticmethod
    def _apply_command_to_state(
        state: DeviceState,
        command: str,
        params: dict[str, Any],
    ) -> DeviceState:
        import dataclasses
        new = dataclasses.replace(state)
        if command == "turn_on":
            new.power = True
        elif command == "turn_off":
            new.power = False
        elif command == "set_volume":
            new.volume = max(0, min(100, int(params.get("value", 50))))
        elif command == "mute":
            new.extra = {**new.extra, "muted": True}
        elif command == "unmute":
            new.extra = {**new.extra, "muted": False}
        elif command == "set_input":
            new.input_source = str(params.get("value", ""))
        return new

    def get_state(self, device: BaseDevice) -> DeviceState:
        return device.state

    def can_handle(self, device: BaseDevice) -> bool:
        return device.adapter_type == "tv"

    @staticmethod
    def ble_matcher(disc: Any) -> Optional[str]:
        name = (disc.name or "").lower()
        keywords = ("bravia", "samsung tv", "lg tv", "tcl ", " tv", "fire tv")
        if any(k in name for k in keywords):
            return "tv"
        return None
