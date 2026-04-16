"""
Aruba wireless AP API client for Phase 7 — Network Security Agent.

Aruba Instant APs expose a REST API (AOS 8.x) on the virtual controller IP.
This client wraps:
  - /v1/clients        → connected wireless clients
  - /v1/aps            → access point inventory + status
  - /v1/rogue_aps      → rogue AP detections
  - /v1/ssids          → SSID configuration
  - /v1/clients/{mac}/disconnect → kick a client
  - /v1/clients/{mac}/blacklist  → blacklist a client MAC

Auth: session token obtained via POST /v1/login.
Base URL: JARVIS_ARUBA_URL (e.g. http://192.168.1.100:4343)
Credentials: JARVIS_ARUBA_USER / JARVIS_ARUBA_PASS

If not configured, all methods return empty/stub results.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10


class ArubaClient:
    """HTTP client for the Aruba Instant AP REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        _session: Any = None,
    ):
        self.base_url = (base_url or os.getenv("JARVIS_ARUBA_URL", "")).rstrip("/")
        self.username = username or os.getenv("JARVIS_ARUBA_USER", "admin")
        self.password = password or os.getenv("JARVIS_ARUBA_PASS", "")
        self.timeout  = timeout
        self._session = _session
        self._token: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.password)

    def _get_session(self) -> Any:
        if self._session is not None:
            return self._session
        import requests
        s = requests.Session()
        s.verify = False   # Aruba APs use self-signed certs on LAN
        return s

    def _ensure_auth(self) -> bool:
        """Obtain a session token if we don't have one yet."""
        if self._token:
            return True
        if not self.configured:
            return False
        try:
            session = self._get_session()
            resp = session.post(
                f"{self.base_url}/v1/login",
                json={"username": self.username, "password": self.password},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data.get("_global_result", {}).get("X-CSRF-Token") or data.get("token")
            if self._session is None:
                session.headers.update({"X-CSRF-Token": self._token or ""})
            return bool(self._token)
        except Exception as exc:
            logger.warning("Aruba auth failed: %s", exc)
            return False

    def _get(self, path: str, params: dict | None = None) -> dict | list | None:
        if not self._ensure_auth():
            logger.debug("Aruba not configured/auth failed, skipping GET %s", path)
            return None
        try:
            session = self._get_session()
            if hasattr(session, "headers"):
                session.headers.update({"X-CSRF-Token": self._token or ""})
            resp = session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Aruba GET %s failed: %s", path, exc)
            return None

    def _post(self, path: str, json_body: dict) -> dict | None:
        if not self._ensure_auth():
            return None
        try:
            session = self._get_session()
            if hasattr(session, "headers"):
                session.headers.update({"X-CSRF-Token": self._token or ""})
            resp = session.post(
                f"{self.base_url}{path}",
                json=json_body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Aruba POST %s failed: %s", path, exc)
            return None

    # ── Clients ────────────────────────────────────────────────────────────────

    def get_clients(self) -> list[dict]:
        """
        Return all connected wireless clients.
        Each dict: mac, ip, name, ssid, ap_name, channel, signal, vlan, os_type.
        """
        raw = self._get("/v1/clients")
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        # Aruba wraps results in {"_data": [...]}
        return raw.get("_data", raw.get("clients", raw.get("results", [])))

    def disconnect_client(self, mac: str) -> bool:
        """Force-disconnect a wireless client by MAC address."""
        raw = self._post(f"/v1/clients/{mac}/disconnect", {})
        return raw is not None

    def blacklist_client(self, mac: str, reason: str = "") -> bool:
        """Add a client MAC to the Aruba blacklist (blocks association)."""
        raw = self._post(f"/v1/clients/{mac}/blacklist", {"reason": reason})
        return raw is not None

    def remove_from_blacklist(self, mac: str) -> bool:
        """Remove a MAC from the Aruba blacklist."""
        raw = self._post(f"/v1/clients/{mac}/unblacklist", {})
        return raw is not None

    # ── Access Points ──────────────────────────────────────────────────────────

    def get_aps(self) -> list[dict]:
        """
        Return all managed access points.
        Each dict: name, ip, mac, model, status, clients, channel_2ghz, channel_5ghz, uptime.
        """
        raw = self._get("/v1/aps")
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return raw.get("_data", raw.get("aps", raw.get("results", [])))

    # ── Rogue APs ──────────────────────────────────────────────────────────────

    def get_rogue_aps(self) -> list[dict]:
        """
        Return rogue/interfering APs detected by Aruba.
        Each dict: ssid, bssid, channel, rssi, classification (rogue/neighbor/interfering).
        """
        raw = self._get("/v1/rogue_aps")
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return raw.get("_data", raw.get("rogues", raw.get("results", [])))

    # ── SSIDs ──────────────────────────────────────────────────────────────────

    def get_ssids(self) -> list[dict]:
        """Return all configured SSIDs with their settings."""
        raw = self._get("/v1/ssids")
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return raw.get("_data", raw.get("ssids", raw.get("results", [])))

    def set_guest_bandwidth(self, ssid: str, mbps_down: float, mbps_up: float) -> bool:
        """Apply bandwidth limits to the guest SSID."""
        raw = self._post(f"/v1/ssids/{ssid}/bandwidth", {
            "download_mbps": mbps_down,
            "upload_mbps":   mbps_up,
        })
        return raw is not None

    # ── VLAN management ────────────────────────────────────────────────────────

    def move_client_to_vlan(self, mac: str, vlan_id: int) -> bool:
        """
        Move a client to a different VLAN (e.g. VLAN 99 = quarantine).
        Implemented via Aruba's user-role or VLAN override mechanism.
        """
        raw = self._post(f"/v1/clients/{mac}/vlan", {"vlan_id": vlan_id})
        return raw is not None

    # ── Network health ─────────────────────────────────────────────────────────

    def get_ap_stats(self, ap_name: str | None = None) -> list[dict]:
        """Return per-AP radio statistics."""
        path = f"/v1/aps/{ap_name}/stats" if ap_name else "/v1/aps/stats"
        raw = self._get(path)
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return raw.get("_data", raw.get("stats", []))

    def get_client_count(self) -> dict[str, int]:
        """Return client count per SSID/AP."""
        clients = self.get_clients()
        counts: dict[str, int] = {}
        for c in clients:
            ssid = c.get("ssid", "unknown")
            counts[ssid] = counts.get(ssid, 0) + 1
        return counts
