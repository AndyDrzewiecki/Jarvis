"""
Firewalla API client for Phase 7 — Network Security Agent.

Firewalla Gold/Purple runs a local REST API on the LAN. This client wraps:
  - /v1/devices        → list all network devices
  - /v1/flows          → recent traffic flows
  - /v1/rules          → firewall rules (CRUD)
  - /v1/alarms         → security alarms/threats

Auth: Bearer token passed as JARVIS_FIREWALLA_TOKEN env var.
Base URL: JARVIS_FIREWALLA_URL (e.g. http://192.168.1.1:8833)

If not configured, all methods return empty/stub results so the rest of
the security module degrades gracefully.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10   # seconds


class FirewallaClient:
    """HTTP client for the Firewalla local REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        _session: Any = None,
    ):
        self.base_url = (base_url or os.getenv("JARVIS_FIREWALLA_URL", "")).rstrip("/")
        self.token    = token or os.getenv("JARVIS_FIREWALLA_TOKEN", "")
        self.timeout  = timeout
        self._session = _session   # injectable for tests

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    def _get_session(self) -> Any:
        if self._session is not None:
            return self._session
        import requests
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {self.token}"})
        return s

    def _get(self, path: str, params: dict | None = None) -> dict | list | None:
        """Perform a GET request. Returns None on any error."""
        if not self.configured:
            logger.debug("Firewalla not configured, skipping GET %s", path)
            return None
        try:
            resp = self._get_session().get(
                f"{self.base_url}{path}",
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Firewalla GET %s failed: %s", path, exc)
            return None

    def _post(self, path: str, json_body: dict) -> dict | None:
        if not self.configured:
            return None
        try:
            resp = self._get_session().post(
                f"{self.base_url}{path}",
                json=json_body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Firewalla POST %s failed: %s", path, exc)
            return None

    def _delete(self, path: str) -> bool:
        if not self.configured:
            return False
        try:
            resp = self._get_session().delete(
                f"{self.base_url}{path}",
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("Firewalla DELETE %s failed: %s", path, exc)
            return False

    # ── Devices ───────────────────────────────────────────────────────────────

    def get_devices(self) -> list[dict]:
        """
        Return all devices Firewalla has seen.
        Each dict contains at minimum: mac, ip, name, vendor, online, blocked.
        """
        raw = self._get("/v1/devices")
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return raw.get("devices", raw.get("results", []))

    # ── Traffic flows ─────────────────────────────────────────────────────────

    def get_flows(
        self,
        limit: int = 100,
        hours: int = 1,
        mac: str | None = None,
    ) -> list[dict]:
        """
        Return recent traffic flows.
        Each flow has: ts, sh (src host), dh (dst host), sp, dp, ob (out bytes),
        rb (recv bytes), du (duration), pr (protocol), ct (category), fd (direction).
        """
        params: dict = {"count": limit, "hours": hours}
        if mac:
            params["mac"] = mac
        raw = self._get("/v1/flows", params=params)
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return raw.get("flows", raw.get("results", []))

    # ── Alarms / Threats ──────────────────────────────────────────────────────

    def get_alarms(self, active_only: bool = True, limit: int = 50) -> list[dict]:
        """
        Return security alarms from Firewalla.
        Each alarm has: aid, type, device.mac, device.ip, remote.ip, ts, severity, message.
        """
        params: dict = {"count": limit}
        if active_only:
            params["status"] = "active"
        raw = self._get("/v1/alarms", params=params)
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return raw.get("alarms", raw.get("results", []))

    def resolve_alarm(self, alarm_id: str) -> bool:
        """Mark a Firewalla alarm as resolved."""
        raw = self._post(f"/v1/alarms/{alarm_id}/resolve", {})
        return raw is not None

    # ── Firewall rules ────────────────────────────────────────────────────────

    def get_rules(self) -> list[dict]:
        """Return all active firewall rules."""
        raw = self._get("/v1/rules")
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return raw.get("rules", raw.get("results", []))

    def create_block_rule(
        self,
        target: str,
        target_type: str = "ip",
        device_mac: str = "",
        direction: str = "both",
        reason: str = "",
    ) -> Optional[str]:
        """
        Create a block rule on Firewalla.
        Returns the Firewalla rule ID on success, None on failure.
        """
        body: dict = {
            "type": "block",
            "target": {"type": target_type, "value": target},
            "direction": direction,
            "memo": reason or f"Auto-blocked by Jarvis security agent",
        }
        if device_mac:
            body["device"] = {"mac": device_mac}

        raw = self._post("/v1/rules", body)
        if raw and isinstance(raw, dict):
            return raw.get("id") or raw.get("rule_id") or raw.get("rid")
        return None

    def delete_rule(self, firewalla_rule_id: str) -> bool:
        """Delete a Firewalla rule by its ID."""
        return self._delete(f"/v1/rules/{firewalla_rule_id}")

    # ── Network stats ─────────────────────────────────────────────────────────

    def get_stats(self, hours: int = 24) -> dict:
        """Return aggregate network stats (bytes in/out, top talkers, etc.)."""
        raw = self._get("/v1/stats", params={"hours": hours})
        if not raw or not isinstance(raw, dict):
            return {}
        return raw

    def get_target_lists(self) -> list[dict]:
        """Return Firewalla target lists (blocklists, allowlists)."""
        raw = self._get("/v1/target_lists")
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return raw.get("target_lists", [])

    def add_to_target_list(self, list_id: str, targets: list[str]) -> bool:
        """Add IPs or domains to a Firewalla target list."""
        raw = self._post(f"/v1/target_lists/{list_id}/targets", {"targets": targets})
        return raw is not None
