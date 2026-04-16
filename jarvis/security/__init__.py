"""
Phase 7 — Network Security Agent module.

Public surface:
  Models:
    NetworkDevice, ThreatEvent, FirewallRule, TrafficFlow
    AnomalyAlert, GuestSession, AuditLogEntry, BlockEntry, DeviceIsolation
    ThreatLevel, ThreatCategory, NetworkDeviceType, VLANType, RuleAction

  Clients:
    FirewallaClient  — Firewalla local REST API
    ArubaClient      — Aruba Instant AP REST API

  Core engines:
    DeviceInventory  — SQLite network device registry
    ThreatEngine     — threat scoring + event log
    AnomalyDetector  — baseline traffic + anomaly detection
    ActiveDefense    — auto-block, isolate, guest management
    AuditLogger      — persistent security audit log
    AccessController — network ACL for the API server
    IntrusionMonitor — brute-force detection
    SecurityScanner  — host-level security checks
"""
from jarvis.security.models import (
    NetworkDevice,
    ThreatEvent,
    FirewallRule,
    TrafficFlow,
    AnomalyAlert,
    GuestSession,
    AuditLogEntry,
    BlockEntry,
    DeviceIsolation,
    ThreatLevel,
    ThreatCategory,
    NetworkDeviceType,
    VLANType,
    RuleAction,
)
from jarvis.security.firewalla_client import FirewallaClient
from jarvis.security.aruba_client import ArubaClient
from jarvis.security.device_inventory import DeviceInventory
from jarvis.security.threat_engine import ThreatEngine
from jarvis.security.anomaly_detector import AnomalyDetector
from jarvis.security.active_defense import ActiveDefense
from jarvis.security.db_protection import (
    AuditLogger,
    AccessController,
    IntrusionMonitor,
    SecurityScanner,
)

__all__ = [
    # Models
    "NetworkDevice", "ThreatEvent", "FirewallRule", "TrafficFlow",
    "AnomalyAlert", "GuestSession", "AuditLogEntry", "BlockEntry", "DeviceIsolation",
    "ThreatLevel", "ThreatCategory", "NetworkDeviceType", "VLANType", "RuleAction",
    # Clients
    "FirewallaClient", "ArubaClient",
    # Engines
    "DeviceInventory", "ThreatEngine", "AnomalyDetector", "ActiveDefense",
    "AuditLogger", "AccessController", "IntrusionMonitor", "SecurityScanner",
]
