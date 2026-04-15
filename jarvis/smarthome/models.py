"""
Smart Home data models for Phase 6.

Defines the core domain types:
  DeviceType     — enum of supported device categories
  DeviceState    — current state snapshot for any device
  BaseDevice     — device registration record
  CommandResult  — result of sending a command to a device
  AutomationTrigger — when a rule fires
  AutomationAction  — what a rule does
  AutomationRule    — complete rule (trigger + actions + metadata)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class DeviceType(str, Enum):
    LIGHT = "light"
    SWITCH = "switch"
    THERMOSTAT = "thermostat"
    TV = "tv"
    SPEAKER = "speaker"
    APPLIANCE = "appliance"       # Instant Pot, Camp Chef, etc.
    SENSOR = "sensor"             # motion, door, temp, humidity
    LOCK = "lock"
    CAMERA = "camera"
    FAN = "fan"
    GENERIC = "generic"


class Protocol(str, Enum):
    BLE = "ble"
    MQTT = "mqtt"
    ZIGBEE = "zigbee"
    ZWAVE = "zwave"
    IR = "ir"
    CEC = "cec"                   # HDMI-CEC for TVs
    HTTP = "http"                 # Cloud/local REST devices
    VIRTUAL = "virtual"           # software-only / mock devices


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"
    PAIRING = "pairing"
    ERROR = "error"


@dataclass
class DeviceState:
    """Current state of a device — power, brightness, temperature, etc."""
    power: Optional[bool] = None          # True = on, False = off
    brightness: Optional[int] = None      # 0–100 percent
    color_temp: Optional[int] = None      # Kelvin, e.g. 2700–6500
    color_rgb: Optional[tuple[int, int, int]] = None
    temperature_f: Optional[float] = None  # thermostat/sensor
    target_temp_f: Optional[float] = None  # thermostat set-point
    mode: Optional[str] = None             # cook mode, fan speed, etc.
    volume: Optional[int] = None           # 0–100
    input_source: Optional[str] = None     # TV input
    lock_state: Optional[str] = None       # "locked" / "unlocked"
    motion_detected: Optional[bool] = None
    extra: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"updated_at": self.updated_at}
        if self.power is not None:
            d["power"] = self.power
        if self.brightness is not None:
            d["brightness"] = self.brightness
        if self.color_temp is not None:
            d["color_temp"] = self.color_temp
        if self.color_rgb is not None:
            d["color_rgb"] = list(self.color_rgb)
        if self.temperature_f is not None:
            d["temperature_f"] = self.temperature_f
        if self.target_temp_f is not None:
            d["target_temp_f"] = self.target_temp_f
        if self.mode is not None:
            d["mode"] = self.mode
        if self.volume is not None:
            d["volume"] = self.volume
        if self.input_source is not None:
            d["input_source"] = self.input_source
        if self.lock_state is not None:
            d["lock_state"] = self.lock_state
        if self.motion_detected is not None:
            d["motion_detected"] = self.motion_detected
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DeviceState":
        color_rgb = d.get("color_rgb")
        if isinstance(color_rgb, list) and len(color_rgb) == 3:
            color_rgb = tuple(color_rgb)  # type: ignore[assignment]
        return cls(
            power=d.get("power"),
            brightness=d.get("brightness"),
            color_temp=d.get("color_temp"),
            color_rgb=color_rgb,
            temperature_f=d.get("temperature_f"),
            target_temp_f=d.get("target_temp_f"),
            mode=d.get("mode"),
            volume=d.get("volume"),
            input_source=d.get("input_source"),
            lock_state=d.get("lock_state"),
            motion_detected=d.get("motion_detected"),
            extra=d.get("extra", {}),
            updated_at=d.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class BaseDevice:
    """A registered smart home device."""
    device_id: str
    display_name: str
    device_type: DeviceType
    protocol: Protocol
    room: str                                  # "kitchen", "garage", "bedroom", etc.
    address: str = ""                          # BLE MAC, MQTT topic, IP, etc.
    manufacturer: str = ""
    model: str = ""
    adapter_type: str = "generic"              # which DeviceAdapter handles this
    status: DeviceStatus = DeviceStatus.UNKNOWN
    state: DeviceState = field(default_factory=DeviceState)
    capabilities: list[str] = field(default_factory=list)  # ["power", "brightness", …]
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_seen: Optional[str] = None

    @classmethod
    def new(
        cls,
        display_name: str,
        device_type: DeviceType,
        protocol: Protocol,
        room: str,
        **kwargs: Any,
    ) -> "BaseDevice":
        return cls(
            device_id=str(uuid.uuid4()),
            display_name=display_name,
            device_type=device_type,
            protocol=protocol,
            room=room,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "display_name": self.display_name,
            "device_type": self.device_type.value,
            "protocol": self.protocol.value,
            "room": self.room,
            "address": self.address,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "adapter_type": self.adapter_type,
            "status": self.status.value,
            "state": self.state.to_dict(),
            "capabilities": self.capabilities,
            "metadata": self.metadata,
            "registered_at": self.registered_at,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BaseDevice":
        return cls(
            device_id=d["device_id"],
            display_name=d["display_name"],
            device_type=DeviceType(d["device_type"]),
            protocol=Protocol(d["protocol"]),
            room=d.get("room", "unknown"),
            address=d.get("address", ""),
            manufacturer=d.get("manufacturer", ""),
            model=d.get("model", ""),
            adapter_type=d.get("adapter_type", "generic"),
            status=DeviceStatus(d.get("status", "unknown")),
            state=DeviceState.from_dict(d.get("state", {})),
            capabilities=d.get("capabilities", []),
            metadata=d.get("metadata", {}),
            registered_at=d.get("registered_at", datetime.now(timezone.utc).isoformat()),
            last_seen=d.get("last_seen"),
        )


@dataclass
class CommandResult:
    """Result of issuing a command to a device."""
    success: bool
    device_id: str
    command: str
    message: str = ""
    new_state: Optional[DeviceState] = None
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "success": self.success,
            "device_id": self.device_id,
            "command": self.command,
            "message": self.message,
            "executed_at": self.executed_at,
        }
        if self.new_state is not None:
            d["new_state"] = self.new_state.to_dict()
        return d


# ── Automation rule types ─────────────────────────────────────────────────────

class TriggerType(str, Enum):
    TIME = "time"                # cron expression or HH:MM
    SENSOR = "sensor"            # device state change
    VOICE = "voice"              # spoken phrase match
    MANUAL = "manual"            # API / UI trigger only
    SUNRISE = "sunrise"
    SUNSET = "sunset"


class ActionType(str, Enum):
    DEVICE_COMMAND = "device_command"   # send command to a device
    SCENE = "scene"                      # activate a named scene
    NOTIFY = "notify"                    # send notification
    DELAY = "delay"                      # wait N seconds
    CONDITION = "condition"              # branch on state


@dataclass
class AutomationTrigger:
    trigger_type: TriggerType
    # TIME triggers
    cron: Optional[str] = None           # cron expression e.g. "0 21 * * *"
    time_str: Optional[str] = None       # "21:00" shorthand
    # SENSOR triggers
    device_id: Optional[str] = None
    attribute: Optional[str] = None      # "motion_detected", "power", etc.
    value: Optional[Any] = None          # expected value / threshold
    # VOICE triggers
    phrase: Optional[str] = None         # "goodnight", "leaving"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in {
            "trigger_type": self.trigger_type.value,
            "cron": self.cron,
            "time_str": self.time_str,
            "device_id": self.device_id,
            "attribute": self.attribute,
            "value": self.value,
            "phrase": self.phrase,
        }.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AutomationTrigger":
        return cls(
            trigger_type=TriggerType(d["trigger_type"]),
            cron=d.get("cron"),
            time_str=d.get("time_str"),
            device_id=d.get("device_id"),
            attribute=d.get("attribute"),
            value=d.get("value"),
            phrase=d.get("phrase"),
        )


@dataclass
class AutomationAction:
    action_type: ActionType
    device_id: Optional[str] = None
    command: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)
    scene_name: Optional[str] = None
    message: Optional[str] = None
    delay_seconds: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in {
            "action_type": self.action_type.value,
            "device_id": self.device_id,
            "command": self.command,
            "params": self.params if self.params else None,
            "scene_name": self.scene_name,
            "message": self.message,
            "delay_seconds": self.delay_seconds,
        }.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AutomationAction":
        return cls(
            action_type=ActionType(d["action_type"]),
            device_id=d.get("device_id"),
            command=d.get("command"),
            params=d.get("params", {}),
            scene_name=d.get("scene_name"),
            message=d.get("message"),
            delay_seconds=d.get("delay_seconds"),
        )


@dataclass
class AutomationRule:
    rule_id: str
    name: str
    enabled: bool
    trigger: AutomationTrigger
    actions: list[AutomationAction]
    description: str = ""
    run_count: int = 0
    last_triggered: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def new(
        cls,
        name: str,
        trigger: AutomationTrigger,
        actions: list[AutomationAction],
        description: str = "",
        enabled: bool = True,
    ) -> "AutomationRule":
        return cls(
            rule_id=str(uuid.uuid4()),
            name=name,
            enabled=enabled,
            trigger=trigger,
            actions=actions,
            description=description,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "enabled": self.enabled,
            "description": self.description,
            "trigger": self.trigger.to_dict(),
            "actions": [a.to_dict() for a in self.actions],
            "run_count": self.run_count,
            "last_triggered": self.last_triggered,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AutomationRule":
        return cls(
            rule_id=d["rule_id"],
            name=d["name"],
            enabled=d.get("enabled", True),
            description=d.get("description", ""),
            trigger=AutomationTrigger.from_dict(d["trigger"]),
            actions=[AutomationAction.from_dict(a) for a in d.get("actions", [])],
            run_count=d.get("run_count", 0),
            last_triggered=d.get("last_triggered"),
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
        )
