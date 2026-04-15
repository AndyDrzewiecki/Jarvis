"""
BLE Scanner — discovers and monitors Bluetooth Low Energy devices.

Uses the `bleak` library when available (graceful degradation if absent).
The scanner maintains a list of discovered devices and fires callbacks
on discovery. Device-specific adapters register matchers to claim devices
they know how to handle.

Usage:
    scanner = BLEScanner()
    found = scanner.scan(timeout=5.0)   # blocking scan
    for d in found:
        print(d["address"], d["name"], d["rssi"])
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Optional bleak import — scanner works in mock mode without it.
try:
    from bleak import BleakScanner  # type: ignore[import-untyped]
    _BLEAK_AVAILABLE = True
except ImportError:
    _BLEAK_AVAILABLE = False
    BleakScanner = None  # type: ignore[assignment,misc]


@dataclass
class BLEDiscovery:
    """A single BLE device discovered during a scan."""
    address: str               # MAC or UUID (platform-dependent)
    name: str                  # advertised name, may be empty
    rssi: int                  # signal strength in dBm
    manufacturer_data: dict[int, bytes] = field(default_factory=dict)
    service_uuids: list[str] = field(default_factory=list)
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "rssi": self.rssi,
            "manufacturer_data": {str(k): list(v) for k, v in self.manufacturer_data.items()},
            "service_uuids": self.service_uuids,
            "discovered_at": self.discovered_at,
        }


# Matcher: (BLEDiscovery) -> adapter_type str or None
DeviceMatcher = Callable[[BLEDiscovery], Optional[str]]


class BLEScanner:
    """
    BLE device scanner with matcher-based adapter detection.

    Matchers are registered per adapter. During a scan the scanner calls
    each matcher and annotates the discovery with the first match.
    """

    def __init__(self) -> None:
        self._matchers: list[tuple[str, DeviceMatcher]] = []
        self._last_scan: list[BLEDiscovery] = []

    # ── Matcher registry ──────────────────────────────────────────────────────

    def register_matcher(self, adapter_type: str, matcher: DeviceMatcher) -> None:
        """Register a matcher function for an adapter type."""
        self._matchers.append((adapter_type, matcher))

    def _match(self, disc: BLEDiscovery) -> Optional[str]:
        for adapter_type, matcher in self._matchers:
            try:
                if matcher(disc):
                    return adapter_type
            except Exception:
                pass
        return None

    # ── Scanning ──────────────────────────────────────────────────────────────

    def scan(self, timeout: float = 5.0) -> list[BLEDiscovery]:
        """
        Perform a synchronous BLE scan. Returns discovered devices.
        If bleak is not installed returns an empty list.
        """
        if not _BLEAK_AVAILABLE:
            logger.warning("bleak not installed — BLE scan unavailable; returning empty list")
            return []
        try:
            return asyncio.run(self._async_scan(timeout))
        except RuntimeError:
            # Already inside an event loop (e.g. FastAPI)
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._async_scan(timeout))

    async def async_scan(self, timeout: float = 5.0) -> list[BLEDiscovery]:
        """Async variant for use inside an existing event loop."""
        if not _BLEAK_AVAILABLE:
            logger.warning("bleak not installed — BLE scan unavailable")
            return []
        return await self._async_scan(timeout)

    async def _async_scan(self, timeout: float) -> list[BLEDiscovery]:
        discoveries: list[BLEDiscovery] = []
        try:
            devices = await BleakScanner.discover(timeout=timeout)
            for dev in devices:
                md: dict[int, bytes] = {}
                uuids: list[str] = []
                if hasattr(dev, "metadata"):
                    md = dev.metadata.get("manufacturer_data", {})
                    uuids = dev.metadata.get("uuids", [])
                disc = BLEDiscovery(
                    address=str(dev.address),
                    name=str(dev.name or ""),
                    rssi=int(dev.rssi or 0),
                    manufacturer_data=md,
                    service_uuids=uuids,
                )
                discoveries.append(disc)
        except Exception as exc:
            logger.error("BLE scan error: %s", exc)
        self._last_scan = discoveries
        return discoveries

    def last_scan(self) -> list[BLEDiscovery]:
        """Return results from the most recent scan."""
        return list(self._last_scan)

    def classify(self, discoveries: list[BLEDiscovery]) -> list[dict[str, Any]]:
        """
        Run matchers against a list of discoveries.
        Returns list of dicts with device info + matched adapter_type.
        """
        results = []
        for disc in discoveries:
            adapter_type = self._match(disc)
            entry = disc.to_dict()
            entry["adapter_type"] = adapter_type or "unknown"
            results.append(entry)
        return results

    @property
    def bleak_available(self) -> bool:
        return _BLEAK_AVAILABLE
