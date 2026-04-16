"""
Database protection and audit logging for Phase 7 — Network Security Agent.

Provides:
  - AuditLogger: SQLite audit log for all security actions and API accesses
  - AccessController: network-level access control list for the FastAPI server
  - IntrusionMonitor: detects repeated failed access attempts (brute-force)
  - SecurityScanner: checks for suspicious local processes / open ports

All security-sensitive state is stored in a dedicated SQLite database
(separate from the main Jarvis databases) so it can be independently
backed up and monitored.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from jarvis.security.models import AuditLogEntry

logger = logging.getLogger(__name__)

_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    entry_id   TEXT PRIMARY KEY,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    target     TEXT DEFAULT '',
    ip_address TEXT DEFAULT '',
    method     TEXT DEFAULT '',
    endpoint   TEXT DEFAULT '',
    status     TEXT DEFAULT 'success',
    detail     TEXT DEFAULT '',
    logged_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_al_actor   ON audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_al_action  ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_al_ip      ON audit_log(ip_address);
CREATE INDEX IF NOT EXISTS idx_al_logged  ON audit_log(logged_at);

CREATE TABLE IF NOT EXISTS access_control (
    cidr       TEXT PRIMARY KEY,
    policy     TEXT NOT NULL,   -- 'allow' or 'deny'
    reason     TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS failed_attempts (
    ip_address  TEXT NOT NULL,
    endpoint    TEXT NOT NULL,
    count       INTEGER DEFAULT 1,
    first_at    TEXT NOT NULL,
    last_at     TEXT NOT NULL,
    PRIMARY KEY (ip_address, endpoint)
);
"""

# Number of failed attempts before flagging as brute-force
BRUTE_FORCE_THRESHOLD = 10
BRUTE_FORCE_WINDOW_MINUTES = 5


class AuditLogger:
    """Persistent audit log for all security-relevant actions."""

    def __init__(self, db_path: str | None = None):
        from jarvis import config
        self._db_path = db_path or os.path.join(config.DATA_DIR, "security_audit.db")

    def _open(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_AUDIT_DDL)
        conn.commit()
        return conn

    def log(
        self,
        actor: str,
        action: str,
        target: str = "",
        ip_address: str = "",
        method: str = "",
        endpoint: str = "",
        status: str = "success",
        detail: str = "",
    ) -> AuditLogEntry:
        """Write an audit log entry."""
        entry = AuditLogEntry.new(
            actor=actor,
            action=action,
            target=target,
            ip_address=ip_address,
            method=method,
            endpoint=endpoint,
            status=status,
            detail=detail,
        )
        conn = self._open()
        try:
            conn.execute(
                """INSERT INTO audit_log
                   (entry_id, actor, action, target, ip_address, method, endpoint, status, detail, logged_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (entry.entry_id, entry.actor, entry.action, entry.target,
                 entry.ip_address, entry.method, entry.endpoint,
                 entry.status, entry.detail, entry.logged_at),
            )
            conn.commit()
        finally:
            conn.close()
        return entry

    def query(
        self,
        actor: str | None = None,
        action: str | None = None,
        ip_address: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params: list[Any] = []
        if actor:
            sql += " AND actor=?"
            params.append(actor)
        if action:
            sql += " AND action=?"
            params.append(action)
        if ip_address:
            sql += " AND ip_address=?"
            params.append(ip_address)
        if since:
            sql += " AND logged_at>=?"
            params.append(since)
        sql += " ORDER BY logged_at DESC LIMIT ?"
        params.append(limit)

        conn = self._open()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_entry(r) for r in rows]
        finally:
            conn.close()

    def recent(self, n: int = 50) -> list[AuditLogEntry]:
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY logged_at DESC LIMIT ?", (n,)
            ).fetchall()
            return [self._row_to_entry(r) for r in rows]
        finally:
            conn.close()

    def purge_old(self, days: int = 90) -> int:
        """Delete audit entries older than `days` days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = self._open()
        try:
            result = conn.execute("DELETE FROM audit_log WHERE logged_at<?", (cutoff,))
            conn.commit()
            return result.rowcount
        finally:
            conn.close()

    def count_by_action(self, days: int = 7) -> dict[str, int]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT action, COUNT(*) as cnt FROM audit_log WHERE logged_at>=? GROUP BY action ORDER BY cnt DESC",
                (cutoff,),
            ).fetchall()
            return {r["action"]: r["cnt"] for r in rows}
        finally:
            conn.close()

    def _row_to_entry(self, row: sqlite3.Row) -> AuditLogEntry:
        d = dict(row)
        return AuditLogEntry(
            entry_id=d["entry_id"],
            actor=d["actor"],
            action=d["action"],
            target=d.get("target", ""),
            ip_address=d.get("ip_address", ""),
            method=d.get("method", ""),
            endpoint=d.get("endpoint", ""),
            status=d.get("status", "success"),
            detail=d.get("detail", ""),
            logged_at=d["logged_at"],
        )


class AccessController:
    """
    Simple network-level access control list for the Jarvis API server.
    Policies are stored in the audit DB and consulted per-request.
    """

    def __init__(self, db_path: str | None = None):
        from jarvis import config
        self._db_path = db_path or os.path.join(config.DATA_DIR, "security_audit.db")

    def _open(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_AUDIT_DDL)
        conn.commit()
        return conn

    def add_rule(self, cidr: str, policy: str, reason: str = "") -> None:
        """Add or update an ACL rule. policy: 'allow' or 'deny'."""
        assert policy in ("allow", "deny"), "policy must be 'allow' or 'deny'"
        now = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO access_control (cidr, policy, reason, created_at) VALUES (?,?,?,?)",
                (cidr, policy, reason, now),
            )
            conn.commit()
        finally:
            conn.close()

    def remove_rule(self, cidr: str) -> bool:
        conn = self._open()
        try:
            result = conn.execute("DELETE FROM access_control WHERE cidr=?", (cidr,))
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    def get_rules(self) -> list[dict]:
        conn = self._open()
        try:
            rows = conn.execute("SELECT * FROM access_control ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def is_allowed(self, ip: str) -> bool:
        """
        Check if an IP is allowed. Default-allow unless a matching deny rule exists.
        Checks exact CIDR matches; for production use a proper IP-in-network check.
        """
        rules = self.get_rules()
        for rule in rules:
            if self._ip_matches(ip, rule["cidr"]):
                return rule["policy"] == "allow"
        return True  # default allow

    @staticmethod
    def _ip_matches(ip: str, cidr: str) -> bool:
        """Basic IP/CIDR match (handles /32 exact matches and simple prefixes)."""
        try:
            import ipaddress
            return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
        except Exception:
            return ip == cidr


class IntrusionMonitor:
    """Detects repeated failed access attempts (brute-force / scanning)."""

    def __init__(self, db_path: str | None = None):
        from jarvis import config
        self._db_path = db_path or os.path.join(config.DATA_DIR, "security_audit.db")

    def _open(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_AUDIT_DDL)
        conn.commit()
        return conn

    def record_failure(self, ip: str, endpoint: str) -> int:
        """
        Record a failed access attempt. Returns the current failure count
        within the brute-force detection window.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        try:
            row = conn.execute(
                "SELECT count, first_at FROM failed_attempts WHERE ip_address=? AND endpoint=?",
                (ip, endpoint),
            ).fetchone()
            if row:
                new_count = row["count"] + 1
                conn.execute(
                    "UPDATE failed_attempts SET count=?, last_at=? WHERE ip_address=? AND endpoint=?",
                    (new_count, now, ip, endpoint),
                )
            else:
                new_count = 1
                conn.execute(
                    "INSERT INTO failed_attempts (ip_address, endpoint, count, first_at, last_at) VALUES (?,?,?,?,?)",
                    (ip, endpoint, new_count, now, now),
                )
            conn.commit()
            return new_count
        finally:
            conn.close()

    def is_brute_force(self, ip: str, endpoint: str = "") -> bool:
        """Return True if the IP has exceeded the failure threshold in the window."""
        window_start = (
            datetime.now(timezone.utc) - timedelta(minutes=BRUTE_FORCE_WINDOW_MINUTES)
        ).isoformat()
        conn = self._open()
        try:
            if endpoint:
                row = conn.execute(
                    "SELECT count FROM failed_attempts WHERE ip_address=? AND endpoint=? AND last_at>=?",
                    (ip, endpoint, window_start),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT SUM(count) as count FROM failed_attempts WHERE ip_address=? AND last_at>=?",
                    (ip, window_start),
                ).fetchone()
            return bool(row and row["count"] and row["count"] >= BRUTE_FORCE_THRESHOLD)
        finally:
            conn.close()

    def get_top_offenders(self, limit: int = 20) -> list[dict]:
        """Return IPs with the most failed attempts in the last 24 hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        conn = self._open()
        try:
            rows = conn.execute(
                """SELECT ip_address, SUM(count) as total, MIN(first_at) as first_at, MAX(last_at) as last_at
                   FROM failed_attempts WHERE last_at>=?
                   GROUP BY ip_address ORDER BY total DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def clear_ip(self, ip: str) -> None:
        conn = self._open()
        try:
            conn.execute("DELETE FROM failed_attempts WHERE ip_address=?", (ip,))
            conn.commit()
        finally:
            conn.close()


class SecurityScanner:
    """
    Lightweight host-level security checks for the Jarvis server machine.
    Checks open ports and running processes for suspicious activity.
    """

    def scan_open_ports(self, host: str = "127.0.0.1", ports: list[int] | None = None) -> list[int]:
        """
        Scan a list of ports on host, return the ones that are open.
        Default ports: common attack surfaces.
        """
        import socket
        check_ports = ports or [21, 22, 23, 25, 53, 80, 135, 139, 443, 445, 3389, 5900, 8080, 8888]
        open_ports: list[int] = []
        for port in check_ports:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    open_ports.append(port)
            except (socket.timeout, ConnectionRefusedError, OSError):
                pass
        return open_ports

    def check_jarvis_db_permissions(self) -> list[dict]:
        """
        Verify Jarvis database files have appropriate permissions.
        Returns a list of issues found.
        """
        from jarvis import config
        issues: list[dict] = []
        db_files = [
            config.MEMORY_DB_PATH,
            config.DECISIONS_DB_PATH,
            config.EPISODES_DB_PATH,
            config.SEMANTIC_DB_PATH,
        ]
        for db_path in db_files:
            if not os.path.exists(db_path):
                continue
            try:
                stat = os.stat(db_path)
                mode = oct(stat.st_mode)[-3:]
                if mode[-1] not in ("0", "4"):  # world-readable or world-writable
                    issues.append({
                        "path": db_path,
                        "mode": mode,
                        "issue": "world-accessible permissions",
                    })
            except Exception as exc:
                issues.append({"path": db_path, "issue": str(exc)})
        return issues

    def get_db_sizes(self) -> dict[str, int]:
        """Return database file sizes in bytes."""
        from jarvis import config
        sizes: dict[str, int] = {}
        db_files = {
            "memory":    config.MEMORY_DB_PATH,
            "decisions": config.DECISIONS_DB_PATH,
            "episodes":  config.EPISODES_DB_PATH,
            "semantic":  config.SEMANTIC_DB_PATH,
        }
        for name, path in db_files.items():
            try:
                sizes[name] = os.path.getsize(path) if os.path.exists(path) else 0
            except Exception:
                sizes[name] = -1
        return sizes

    def integrity_check(self, db_path: str) -> bool:
        """Run SQLite PRAGMA integrity_check on a database file."""
        if not os.path.exists(db_path):
            return True   # non-existent DB is not corrupt
        try:
            conn = sqlite3.connect(db_path)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return result[0] == "ok"
        except Exception as exc:
            logger.warning("Integrity check failed for %s: %s", db_path, exc)
            return False

    def hash_db(self, db_path: str) -> Optional[str]:
        """Return SHA-256 hash of a database file for change detection."""
        if not os.path.exists(db_path):
            return None
        try:
            h = hashlib.sha256()
            with open(db_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None
