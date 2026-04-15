"""
Voice Handler — translates natural language utterances into device commands.

Two-tier parsing:
  1. Pattern matching (fast, no LLM) — handles common phrases like
     "turn on the kitchen lights", "dim the bedroom to 50%", "what's the temperature"
  2. LLM fallback — for complex or ambiguous requests, sends to the Jarvis
     routing brain with smart home context injected

The handler also routes voice triggers to the AutomationEngine for
rule-matching (e.g. "goodnight" fires the goodnight scene).

Room context is injected by the caller (the tablet/device that heard the command)
so "turn off the lights" means the lights in THAT room.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedCommand:
    """Result of parsing a voice utterance."""
    intent: str                    # "turn_on", "turn_off", "set_brightness", etc.
    target: str                    # device name / room / "all"
    params: dict[str, Any] = field(default_factory=dict)
    raw_utterance: str = ""
    confidence: float = 1.0        # 1.0 = pattern match, <1.0 = LLM inference
    ambiguous: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "target": self.target,
            "params": self.params,
            "raw_utterance": self.raw_utterance,
            "confidence": self.confidence,
            "ambiguous": self.ambiguous,
        }


@dataclass
class VoiceResponse:
    """Full response from processing a voice utterance."""
    parsed: ParsedCommand
    device_ids: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    spoken_reply: str = ""
    automation_fired: bool = False


# ── Pattern sets ──────────────────────────────────────────────────────────────

# Matches "turn on" / "turn off" / "switch on" / "switch off" / "power on" / "power off"
_POWER_ON  = re.compile(r"\b(turn|switch|power|flip)\s+on\b", re.I)
_POWER_OFF = re.compile(r"\b(turn|switch|power|flip)\s+off\b", re.I)

# Brightness: "dim to 30" / "set brightness to 80" / "dim the lights to 50%"
_BRIGHTNESS = re.compile(
    r"\b(dim|brighten|set\s+brightness\s+to|set\s+the\s+lights?\s+to)\b.*?(\d{1,3})\s*%?",
    re.I,
)
_BRIGHTNESS_SIMPLE = re.compile(r"\bdim\b", re.I)

# Color temp: "warm" / "cool" / "daylight" / "soft white"
_COLOR_WARM = re.compile(r"\b(warm|candlelight|soft\s+white|relaxed?)\b", re.I)
_COLOR_COOL = re.compile(r"\b(cool|daylight|bright\s+white|focus)\b", re.I)

# Temperature: "set thermostat to 72" / "set temperature to 70 degrees"
_THERMOSTAT = re.compile(
    r"\b(set|change)\s+(the\s+)?(thermostat|temperature|temp|heat|ac|air)\b.*?(\d{2,3})",
    re.I,
)

# Volume: "set volume to 30" / "turn up the volume" / "volume up"
_VOLUME = re.compile(r"\b(set\s+)?volume\s+(to\s+)?(\d{1,3})\b", re.I)
_VOLUME_UP   = re.compile(r"\b(volume\s+up|louder|turn\s+up)\b", re.I)
_VOLUME_DOWN = re.compile(r"\b(volume\s+down|quieter|turn\s+down)\b", re.I)

# Appliance modes: "slow cook" / "pressure cook" / "sauté"
_COOK_MODE = re.compile(
    r"\b(slow\s+cook|pressure\s+cook|saute|sauté|steam|rice|warm|yogurt)\b", re.I
)

# Status query: "what's the temperature" / "is the TV on" / "check the lights"
_STATUS = re.compile(r"\b(what|is|are|check|status|show)\b.*(temp|status|on|off|level)", re.I)

# Room extractor
_ROOM_WORDS = {
    "kitchen", "bedroom", "living room", "garage", "bathroom",
    "office", "basement", "backyard", "patio", "hallway", "dining",
    "master", "kids", "nursery", "laundry",
}

# Specific device type words
_DEVICE_WORDS = {
    "light": "light", "lights": "light", "lamp": "light", "lamps": "light",
    "tv": "tv", "television": "tv",
    "thermostat": "thermostat", "heat": "thermostat", "ac": "thermostat",
    "speaker": "speaker", "music": "speaker",
    "instant pot": "appliance", "instantpot": "appliance",
    "camp chef": "appliance",
    "lock": "lock", "door": "lock",
    "fan": "fan",
}


class VoiceHandler:
    """
    Parses natural language utterances into structured device commands,
    then dispatches them via the registry + automation engine.
    """

    def __init__(
        self,
        registry: Any = None,
        automation_engine: Any = None,
        adapter_registry: Optional[dict[str, Any]] = None,
    ) -> None:
        self._registry = registry
        self._automation = automation_engine
        self._adapters = adapter_registry or {}

    # ── Main entry point ──────────────────────────────────────────────────────

    def process(self, utterance: str, room: str = "unknown") -> VoiceResponse:
        """
        Parse and execute a voice command.
        room = the room where the command was spoken (from device context).
        """
        utterance = utterance.strip()

        # 1. Check automation voice triggers first
        if self._automation:
            fired = self._automation.trigger_by_voice(utterance)
            if fired:
                rule, results = fired[0]
                return VoiceResponse(
                    parsed=ParsedCommand(
                        intent="voice_trigger",
                        target=rule.name,
                        raw_utterance=utterance,
                    ),
                    results=[r.to_dict() for r in results],
                    spoken_reply=f"Done — {rule.name}.",
                    automation_fired=True,
                )

        # 2. Pattern parse
        parsed = self.parse(utterance, room)
        if parsed is None:
            return VoiceResponse(
                parsed=ParsedCommand(
                    intent="unknown",
                    target="",
                    raw_utterance=utterance,
                    confidence=0.0,
                ),
                spoken_reply="Sorry, I didn't understand that smart home command.",
            )

        # 3. Resolve devices
        device_ids = self._resolve_devices(parsed, room)

        # 4. Dispatch commands
        results = []
        for device_id in device_ids:
            result = self._dispatch(device_id, parsed)
            if result:
                results.append(result.to_dict())

        spoken = self._make_reply(parsed, device_ids, results)

        return VoiceResponse(
            parsed=parsed,
            device_ids=device_ids,
            results=results,
            spoken_reply=spoken,
        )

    # ── Parser ────────────────────────────────────────────────────────────────

    def parse(self, utterance: str, room: str = "unknown") -> Optional[ParsedCommand]:
        """Parse utterance into a ParsedCommand. Returns None if no match."""
        u = utterance.lower().strip()

        target_room = self._extract_room(u) or room
        target_device_type = self._extract_device_type(u) or "all"
        target = f"{target_room}/{target_device_type}" if target_room != "unknown" else target_device_type

        # Brightness
        m = _BRIGHTNESS.search(u)
        if m:
            pct = max(0, min(100, int(m.group(2))))
            return ParsedCommand(
                intent="set_brightness", target=target,
                params={"value": pct}, raw_utterance=utterance,
            )

        # Power on
        if _POWER_ON.search(u):
            return ParsedCommand(
                intent="turn_on", target=target, raw_utterance=utterance
            )

        # Power off
        if _POWER_OFF.search(u):
            return ParsedCommand(
                intent="turn_off", target=target, raw_utterance=utterance
            )

        # Dim without percentage → 30%
        if _BRIGHTNESS_SIMPLE.search(u) and "brighten" not in u:
            return ParsedCommand(
                intent="set_brightness", target=target,
                params={"value": 30}, raw_utterance=utterance,
            )

        # Color temperature
        if _COLOR_WARM.search(u):
            return ParsedCommand(
                intent="set_color_temp", target=target,
                params={"value": 2700}, raw_utterance=utterance,
            )
        if _COLOR_COOL.search(u):
            return ParsedCommand(
                intent="set_color_temp", target=target,
                params={"value": 5000}, raw_utterance=utterance,
            )

        # Thermostat
        m = _THERMOSTAT.search(u)
        if m:
            temp = float(m.group(4))
            return ParsedCommand(
                intent="set_temperature", target=target,
                params={"value": temp}, raw_utterance=utterance,
            )

        # Volume
        m = _VOLUME.search(u)
        if m:
            vol = max(0, min(100, int(m.group(3))))
            return ParsedCommand(
                intent="set_volume", target=target,
                params={"value": vol}, raw_utterance=utterance,
            )
        if _VOLUME_UP.search(u):
            return ParsedCommand(
                intent="volume_up", target=target, raw_utterance=utterance
            )
        if _VOLUME_DOWN.search(u):
            return ParsedCommand(
                intent="volume_down", target=target, raw_utterance=utterance
            )

        # Cook mode
        m = _COOK_MODE.search(u)
        if m:
            mode = m.group(0).lower().replace(" ", "_")
            return ParsedCommand(
                intent="set_mode", target=target,
                params={"value": mode}, raw_utterance=utterance,
            )

        # Status query
        if _STATUS.search(u):
            return ParsedCommand(
                intent="get_state", target=target, raw_utterance=utterance,
                confidence=0.8,
            )

        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_room(self, text: str) -> Optional[str]:
        for room in _ROOM_WORDS:
            if room in text:
                return room
        return None

    def _extract_device_type(self, text: str) -> Optional[str]:
        for phrase, dtype in sorted(_DEVICE_WORDS.items(), key=lambda x: -len(x[0])):
            if phrase in text:
                return dtype
        return None

    def _resolve_devices(self, parsed: ParsedCommand, room: str) -> list[str]:
        if self._registry is None:
            return []

        target_room, _, dtype = parsed.target.partition("/")
        if not dtype:
            dtype = target_room
            target_room = room

        devices = self._registry.list_all()
        matched = []
        for dev in devices:
            room_match = (target_room in ("all", "unknown") or dev.room == target_room)
            type_match = (dtype in ("all", "") or dev.device_type.value == dtype)
            if room_match and type_match:
                matched.append(dev.device_id)
        return matched

    def _dispatch(self, device_id: str, parsed: ParsedCommand) -> Optional[Any]:
        if self._registry is None:
            return None
        device = self._registry.get(device_id)
        if device is None:
            return None
        adapter = self._adapters.get(device.adapter_type)
        if adapter is None:
            return None
        result = adapter.send_command(device, parsed.intent, parsed.params)
        if result.success and result.new_state:
            self._registry.update_state(device_id, result.new_state)
        return result

    def _make_reply(
        self,
        parsed: ParsedCommand,
        device_ids: list[str],
        results: list[dict],
    ) -> str:
        n = len(device_ids)
        ok = sum(1 for r in results if r.get("success"))
        noun = "device" if n == 1 else "devices"

        if n == 0:
            return f"I couldn't find any devices matching that request."

        intent = parsed.intent
        if intent == "turn_on":
            return f"Turned on {n} {noun}." if ok == n else f"Turned on {ok}/{n} {noun}."
        if intent == "turn_off":
            return f"Turned off {n} {noun}."
        if intent == "set_brightness":
            pct = parsed.params.get("value", "?")
            return f"Set brightness to {pct}% on {n} {noun}."
        if intent == "set_color_temp":
            val = parsed.params.get("value", "?")
            return f"Set color temperature to {val}K on {n} {noun}."
        if intent == "set_temperature":
            val = parsed.params.get("value", "?")
            return f"Setting temperature to {val}°F."
        if intent == "set_volume":
            val = parsed.params.get("value", "?")
            return f"Volume set to {val}."
        if intent == "set_mode":
            val = parsed.params.get("value", "?")
            return f"Set mode to {val}."
        if intent == "get_state":
            return f"Checking status of {n} {noun}."
        return f"Done."
