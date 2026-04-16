"""
Phase 7 — Network Security Agent data models.

Core domain types:
  NetworkDevice     — a discovered network device (MAC, IP, hostname, vendor)
  ThreatLevel       — enum: info, low, medium, high, critical
  ThreatEvent       — a detected security threat
  FirewallRule      — a Firewalla block/allow rule
  TrafficFlow       — a sampled traffic flow (src/dst/bytes/protocol)
  AnomalyAlert      — a detected traffic anomaly
  GuestSession      — a guest Wi-Fi session
  AuditLogEntry     — an API access audit record
  BlockEntry        — an active block (IP or domain)
  DeviceIsolation   — an active device quarantine record
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class ThreatLevel(str, Enum):
    INFO     = "info"
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class ThreatCategory(str, Enum):
    PORT_SCAN         = "port_scan"
    MALWARE           = "malware"
    BOTNET            = "botnet"
    DATA_EXFILTRATION = "data_exfiltration"
    BRUTE_FORCE       = "brute_force"
    ROGUE_AP          = "rogue_ap"
    SUSPICIOUS_DNS    = "suspicious_dns"
    POLICY_VIOLATION  = "policy_violation"
    ANOMALY           = "anomaly"
    UNKNOWN           = "unknown"


class NetworkDeviceType(str, Enum):
    ROUTER       = "router"
    ACCESS_POINT = "access_point"
    IOT          = "iot"
    COMPUTER     = "computer"
    PHONE        = "phone"
    TABLET       = "tablet"
    SMART_TV     = "smart_tv"
    PRINTER      = "printer"
    CAMERA       = "camera"
    GUEST        = "guest"
    UNKNOWN      = "unknown"


class VLANType(str, Enum):
    MAIN      = "main"       # VLAN 10 — trusted devices
    IOT       = "iot"        # VLAN 20 — IoT devices
    GUEST     = "guest"      # VLAN 30 — guest Wi-Fi
    QUARANTINE = "quarantine" # VLAN 99 — isolated devices


class RuleAction(str, Enum):
    BLOCK = "block"
    ALLOW = "allow"
    RATE_LIMIT = "rate_limit"
    LOG = "log"


# ── Network Device ─────────────────────────────────────────────────────────────

@dataclass
class NetworkDevice:
    """A device discovered on the network."""
    device_id:   str
    mac_address: str
    ip_address:  str
    hostname:    str          = ""
    vendor:      str          = ""
    device_type: NetworkDeviceType = NetworkDeviceType.UNKNOWN
    vlan:        VLANType     = VLANType.MAIN
    ssid:        str          = ""             # Wi-Fi SSID if wireless
    signal_dbm:  Optional[int] = None          # RSSI from Aruba AP
    is_online:   bool         = True
    is_blocked:  bool         = False
    is_isolated: bool         = False
    threat_score: float       = 0.0            # 0.0 – 100.0
    first_seen:  str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_seen:   str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata:    dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(cls, mac: str, ip: str, **kwargs: Any) -> "NetworkDevice":
        return cls(device_id=str(uuid.uuid4()), mac_address=mac, ip_address=ip, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id":   self.device_id,
            "mac_address": self.mac_address,
            "ip_address":  self.ip_address,
            "hostname":    self.hostname,
            "vendor":      self.vendor,
            "device_type": self.device_type.value,
            "vlan":        self.vlan.value,
            "ssid":        self.ssid,
            "signal_dbm":  self.signal_dbm,
            "is_online":   self.is_online,
            "is_blocked":  self.is_blocked,
            "is_isolated": self.is_isolated,
            "threat_score": self.threat_score,
            "first_seen":  self.first_seen,
            "last_seen":   self.last_seen,
            "metadata":    self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NetworkDevice":
        return cls(
            device_id=d["device_id"],
            mac_address=d["mac_address"],
            ip_address=d["ip_address"],
            hostname=d.get("hostname", ""),
            vendor=d.get("vendor", ""),
            device_type=NetworkDeviceType(d.get("device_type", "unknown")),
            vlan=VLANType(d.get("vlan", "main")),
            ssid=d.get("ssid", ""),
            signal_dbm=d.get("signal_dbm"),
            is_online=d.get("is_online", True),
            is_blocked=d.get("is_blocked", False),
            is_isolated=d.get("is_isolated", False),
            threat_score=d.get("threat_score", 0.0),
            first_seen=d.get("first_seen", datetime.now(timezone.utc).isoformat()),
            last_seen=d.get("last_seen", datetime.now(timezone.utc).isoformat()),
            metadata=d.get("metadata", {}),
        )


# ── Threat Event ──────────────────────────────────────────────────────────────

@dataclass
class ThreatEvent:
    """A detected security threat."""
    event_id:   str
    level:      ThreatLevel
    category:   ThreatCategory
    description: str
    source_ip:  str           = ""
    source_mac: str           = ""
    dest_ip:    str           = ""
    dest_port:  Optional[int] = None
    protocol:   str           = ""
    device_id:  str           = ""
    auto_blocked: bool        = False
    resolved:   bool          = False
    score:      float         = 0.0
    raw_data:   dict[str, Any] = field(default_factory=dict)
    detected_at: str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None

    @classmethod
    def new(cls, level: ThreatLevel, category: ThreatCategory, description: str, **kwargs: Any) -> "ThreatEvent":
        return cls(event_id=str(uuid.uuid4()), level=level, category=category, description=description, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id":     self.event_id,
            "level":        self.level.value,
            "category":     self.category.value,
            "description":  self.description,
            "source_ip":    self.source_ip,
            "source_mac":   self.source_mac,
            "dest_ip":      self.dest_ip,
            "dest_port":    self.dest_port,
            "protocol":     self.protocol,
            "device_id":    self.device_id,
            "auto_blocked": self.auto_blocked,
            "resolved":     self.resolved,
            "score":        self.score,
            "raw_data":     self.raw_data,
            "detected_at":  self.detected_at,
            "resolved_at":  self.resolved_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ThreatEvent":
        return cls(
            event_id=d["event_id"],
            level=ThreatLevel(d["level"]),
            category=ThreatCategory(d["category"]),
            description=d["description"],
            source_ip=d.get("source_ip", ""),
            source_mac=d.get("source_mac", ""),
            dest_ip=d.get("dest_ip", ""),
            dest_port=d.get("dest_port"),
            protocol=d.get("protocol", ""),
            device_id=d.get("device_id", ""),
            auto_blocked=d.get("auto_blocked", False),
            resolved=d.get("resolved", False),
            score=d.get("score", 0.0),
            raw_data=d.get("raw_data", {}),
            detected_at=d.get("detected_at", datetime.now(timezone.utc).isoformat()),
            resolved_at=d.get("resolved_at"),
        )


# ── Firewall Rule ──────────────────────────────────────────────────────────────

@dataclass
class FirewallRule:
    """A network firewall rule (maps to a Firewalla rule)."""
    rule_id:    str
    action:     RuleAction
    target:     str           # IP, CIDR, or domain
    target_type: str          = "ip"          # "ip", "domain", "cidr"
    direction:  str           = "outbound"    # "inbound" / "outbound" / "both"
    protocol:   str           = "any"
    port:       Optional[int] = None
    device_mac: str           = ""            # "" = applies to all devices
    reason:     str           = ""
    auto_created: bool        = False
    expires_at: Optional[str] = None
    created_at: str           = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    firewalla_id: str         = ""            # ID returned by Firewalla API

    @classmethod
    def new(cls, action: RuleAction, target: str, **kwargs: Any) -> "FirewallRule":
        return cls(rule_id=str(uuid.uuid4()), action=action, target=target, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id":      self.rule_id,
            "action":       self.action.value,
            "target":       self.target,
            "target_type":  self.target_type,
            "direction":    self.direction,
            "protocol":     self.protocol,
            "port":         self.port,
            "device_mac":   self.device_mac,
            "reason":       self.reason,
            "auto_created": self.auto_created,
            "expires_at":   self.expires_at,
            "created_at":   self.created_at,
            "firewalla_id": self.firewalla_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FirewallRule":
        return cls(
            rule_id=d["rule_id"],
            action=RuleAction(d["action"]),
            target=d["target"],
            target_type=d.get("target_type", "ip"),
            direction=d.get("direction", "outbound"),
            protocol=d.get("protocol", "any"),
            port=d.get("port"),
            device_mac=d.get("device_mac", ""),
            reason=d.get("reason", ""),
            auto_created=d.get("auto_created", False),
            expires_at=d.get("expires_at"),
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
            firewalla_id=d.get("firewalla_id", ""),
        )


# ── Traffic Flow ───────────────────────────────────────────────────────────────

@dataclass
class TrafficFlow:
    """A sampled network traffic flow."""
    flow_id:     str
    src_ip:      str
    dst_ip:      str
    src_mac:     str          = ""
    protocol:    str          = "tcp"
    dst_port:    Optional[int] = None
    bytes_sent:  int          = 0
    bytes_recv:  int          = 0
    duration_s:  float        = 0.0
    category:    str          = ""           # Firewalla traffic category
    app:         str          = ""           # application name if known
    blocked:     bool         = False
    sampled_at:  str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def new(cls, src_ip: str, dst_ip: str, **kwargs: Any) -> "TrafficFlow":
        return cls(flow_id=str(uuid.uuid4()), src_ip=src_ip, dst_ip=dst_ip, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flow_id":    self.flow_id,
            "src_ip":     self.src_ip,
            "dst_ip":     self.dst_ip,
            "src_mac":    self.src_mac,
            "protocol":   self.protocol,
            "dst_port":   self.dst_port,
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "duration_s": self.duration_s,
            "category":   self.category,
            "app":        self.app,
            "blocked":    self.blocked,
            "sampled_at": self.sampled_at,
        }


# ── Anomaly Alert ──────────────────────────────────────────────────────────────

@dataclass
class AnomalyAlert:
    """A detected deviation from baseline traffic patterns."""
    alert_id:    str
    device_mac:  str
    device_ip:   str
    metric:      str          # "bytes_per_hour", "new_destinations", "port_variety"
    baseline:    float        # expected value
    observed:    float        # actual value
    deviation_pct: float      # percent above/below baseline
    level:       ThreatLevel  = ThreatLevel.LOW
    description: str          = ""
    resolved:    bool         = False
    detected_at: str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def new(cls, device_mac: str, device_ip: str, metric: str,
            baseline: float, observed: float, **kwargs: Any) -> "AnomalyAlert":
        deviation = abs((observed - baseline) / max(baseline, 1)) * 100
        return cls(
            alert_id=str(uuid.uuid4()),
            device_mac=device_mac,
            device_ip=device_ip,
            metric=metric,
            baseline=baseline,
            observed=observed,
            deviation_pct=deviation,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id":      self.alert_id,
            "device_mac":    self.device_mac,
            "device_ip":     self.device_ip,
            "metric":        self.metric,
            "baseline":      self.baseline,
            "observed":      self.observed,
            "deviation_pct": round(self.deviation_pct, 1),
            "level":         self.level.value,
            "description":   self.description,
            "resolved":      self.resolved,
            "detected_at":   self.detected_at,
        }


# ── Guest Session ──────────────────────────────────────────────────────────────

@dataclass
class GuestSession:
    """A Wi-Fi guest network session."""
    session_id:  str
    mac_address: str
    ip_address:  str
    hostname:    str          = ""
    bandwidth_limit_mbps: Optional[float] = None
    expires_at:  Optional[str] = None
    is_active:   bool         = True
    bytes_up:    int          = 0
    bytes_down:  int          = 0
    connected_at: str         = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def new(cls, mac: str, ip: str, **kwargs: Any) -> "GuestSession":
        return cls(session_id=str(uuid.uuid4()), mac_address=mac, ip_address=ip, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id":   self.session_id,
            "mac_address":  self.mac_address,
            "ip_address":   self.ip_address,
            "hostname":     self.hostname,
            "bandwidth_limit_mbps": self.bandwidth_limit_mbps,
            "expires_at":   self.expires_at,
            "is_active":    self.is_active,
            "bytes_up":     self.bytes_up,
            "bytes_down":   self.bytes_down,
            "connected_at": self.connected_at,
        }


# ── Audit Log Entry ────────────────────────────────────────────────────────────

@dataclass
class AuditLogEntry:
    """An API access or security action audit record."""
    entry_id:   str
    actor:      str           # "api", "security_agent", "user", etc.
    action:     str           # "block_ip", "api_access", "isolate_device", etc.
    target:     str           = ""
    ip_address: str           = ""
    method:     str           = ""           # HTTP method for API calls
    endpoint:   str           = ""           # API endpoint
    status:     str           = "success"
    detail:     str           = ""
    logged_at:  str           = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def new(cls, actor: str, action: str, **kwargs: Any) -> "AuditLogEntry":
        return cls(entry_id=str(uuid.uuid4()), actor=actor, action=action, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id":   self.entry_id,
            "actor":      self.actor,
            "action":     self.action,
            "target":     self.target,
            "ip_address": self.ip_address,
            "method":     self.method,
            "endpoint":   self.endpoint,
            "status":     self.status,
            "detail":     self.detail,
            "logged_at":  self.logged_at,
        }


# ── Block Entry ────────────────────────────────────────────────────────────────

@dataclass
class BlockEntry:
    """An active block on an IP address or domain."""
    block_id:   str
    target:     str           # IP or domain
    target_type: str          = "ip"
    reason:     str           = ""
    auto_created: bool        = False
    expires_at: Optional[str] = None
    created_at: str           = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    firewalla_rule_id: str    = ""

    @classmethod
    def new(cls, target: str, **kwargs: Any) -> "BlockEntry":
        return cls(block_id=str(uuid.uuid4()), target=target, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id":   self.block_id,
            "target":     self.target,
            "target_type": self.target_type,
            "reason":     self.reason,
            "auto_created": self.auto_created,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "firewalla_rule_id": self.firewalla_rule_id,
        }


# ── Device Isolation ──────────────────────────────────────────────────────────

@dataclass
class DeviceIsolation:
    """An active device quarantine record."""
    isolation_id: str
    device_id:   str
    mac_address: str
    ip_address:  str
    original_vlan: VLANType
    reason:      str          = ""
    threat_event_id: str      = ""
    is_active:   bool         = True
    isolated_at: str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    released_at: Optional[str] = None

    @classmethod
    def new(cls, device_id: str, mac: str, ip: str, original_vlan: VLANType, **kwargs: Any) -> "DeviceIsolation":
        return cls(
            isolation_id=str(uuid.uuid4()),
            device_id=device_id,
            mac_address=mac,
            ip_address=ip,
            original_vlan=original_vlan,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "isolation_id":    self.isolation_id,
            "device_id":       self.device_id,
            "mac_address":     self.mac_address,
            "ip_address":      self.ip_address,
            "original_vlan":   self.original_vlan.value,
            "reason":          self.reason,
            "threat_event_id": self.threat_event_id,
            "is_active":       self.is_active,
            "isolated_at":     self.isolated_at,
            "released_at":     self.released_at,
        }
