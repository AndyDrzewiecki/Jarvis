"""Tests for db_protection: AuditLogger, AccessController, IntrusionMonitor, SecurityScanner."""
import os
import pytest
import tempfile

from jarvis.security.db_protection import (
    AuditLogger, AccessController, IntrusionMonitor,
    SecurityScanner, BRUTE_FORCE_THRESHOLD,
)
from jarvis.security.models import AuditLogEntry


@pytest.fixture
def audit(tmp_path):
    return AuditLogger(db_path=str(tmp_path / "test_audit.db"))


@pytest.fixture
def acl(tmp_path):
    return AccessController(db_path=str(tmp_path / "test_audit.db"))


@pytest.fixture
def monitor(tmp_path):
    return IntrusionMonitor(db_path=str(tmp_path / "test_audit.db"))


class TestAuditLogger:
    def test_log_entry(self, audit):
        entry = audit.log(
            actor="api",
            action="block",
            target="1.2.3.4",
            ip_address="192.168.1.1",
            method="POST",
            endpoint="/api/security/block",
        )
        assert isinstance(entry, AuditLogEntry)
        assert entry.actor == "api"
        assert entry.action == "block"
        assert entry.entry_id

    def test_log_persists(self, audit):
        audit.log("api", "unblock", target="x.com")
        entries = audit.recent(10)
        assert any(e.action == "unblock" for e in entries)

    def test_query_by_actor(self, audit):
        audit.log("api", "block", target="1.1.1.1")
        audit.log("security_agent", "isolate", target="aa:bb")
        results = audit.query(actor="api")
        assert all(e.actor == "api" for e in results)

    def test_query_by_action(self, audit):
        audit.log("api", "block")
        audit.log("api", "unblock")
        results = audit.query(action="block")
        assert all(e.action == "block" for e in results)

    def test_query_by_ip(self, audit):
        audit.log("api", "access", ip_address="10.0.0.5")
        audit.log("api", "access", ip_address="10.0.0.6")
        results = audit.query(ip_address="10.0.0.5")
        assert len(results) == 1

    def test_recent(self, audit):
        for i in range(5):
            audit.log("api", f"action_{i}")
        entries = audit.recent(3)
        assert len(entries) == 3

    def test_count_by_action(self, audit):
        audit.log("api", "block")
        audit.log("api", "block")
        audit.log("api", "unblock")
        counts = audit.count_by_action()
        assert counts.get("block", 0) == 2
        assert counts.get("unblock", 0) == 1

    def test_purge_old(self, audit):
        from datetime import datetime, timezone, timedelta
        old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn = audit._open()
        conn.execute(
            "INSERT INTO audit_log (entry_id,actor,action,target,ip_address,method,endpoint,status,detail,logged_at) VALUES ('old','api','old_action','','','','','success','',?)",
            (old,),
        )
        conn.commit()
        conn.close()
        removed = audit.purge_old(days=90)
        assert removed == 1

    def test_status_field(self, audit):
        audit.log("api", "failed_block", status="failure", detail="rate limited")
        entries = audit.recent(1)
        assert entries[0].status == "failure"


class TestAccessController:
    def test_default_allow(self, acl):
        assert acl.is_allowed("192.168.1.50") is True

    def test_deny_rule(self, acl):
        acl.add_rule("1.2.3.0/24", "deny", reason="known bad subnet")
        assert acl.is_allowed("1.2.3.100") is False

    def test_allow_rule_overrides(self, acl):
        acl.add_rule("1.2.3.4/32", "allow", reason="trusted host")
        assert acl.is_allowed("1.2.3.4") is True

    def test_get_rules(self, acl):
        acl.add_rule("192.168.100.0/24", "deny")
        rules = acl.get_rules()
        assert len(rules) == 1
        assert rules[0]["cidr"] == "192.168.100.0/24"

    def test_remove_rule(self, acl):
        acl.add_rule("5.5.5.0/24", "deny")
        ok = acl.remove_rule("5.5.5.0/24")
        assert ok is True
        assert acl.is_allowed("5.5.5.5") is True

    def test_remove_nonexistent(self, acl):
        assert acl.remove_rule("9.9.9.0/24") is False

    def test_ip_matches_exact(self):
        assert AccessController._ip_matches("1.2.3.4", "1.2.3.4/32") is True
        assert AccessController._ip_matches("1.2.3.4", "1.2.3.5/32") is False

    def test_ip_matches_subnet(self):
        assert AccessController._ip_matches("192.168.1.50", "192.168.1.0/24") is True
        assert AccessController._ip_matches("192.168.2.1", "192.168.1.0/24") is False

    def test_invalid_cidr_returns_string_match(self):
        assert AccessController._ip_matches("1.2.3.4", "1.2.3.4") is True
        assert AccessController._ip_matches("1.2.3.4", "invalid") is False


class TestIntrusionMonitor:
    def test_record_failure(self, monitor):
        count = monitor.record_failure("5.5.5.5", "/api/security")
        assert count == 1
        count2 = monitor.record_failure("5.5.5.5", "/api/security")
        assert count2 == 2

    def test_is_brute_force_true(self, monitor):
        for _ in range(BRUTE_FORCE_THRESHOLD):
            monitor.record_failure("6.6.6.6", "/api/chat")
        assert monitor.is_brute_force("6.6.6.6", "/api/chat") is True

    def test_is_brute_force_false_below_threshold(self, monitor):
        for _ in range(BRUTE_FORCE_THRESHOLD - 1):
            monitor.record_failure("7.7.7.7", "/api/chat")
        assert monitor.is_brute_force("7.7.7.7", "/api/chat") is False

    def test_get_top_offenders(self, monitor):
        for _ in range(5):
            monitor.record_failure("8.8.8.8", "/api/x")
        for _ in range(3):
            monitor.record_failure("9.9.9.9", "/api/y")
        offenders = monitor.get_top_offenders(limit=5)
        assert offenders[0]["ip_address"] == "8.8.8.8"

    def test_clear_ip(self, monitor):
        monitor.record_failure("10.0.0.99", "/api/chat")
        monitor.clear_ip("10.0.0.99")
        assert monitor.is_brute_force("10.0.0.99") is False


class TestSecurityScanner:
    def test_scan_open_ports_returns_list(self):
        scanner = SecurityScanner()
        # Just verify it returns a list and doesn't crash
        ports = scanner.scan_open_ports("127.0.0.1", [9999, 9998])
        assert isinstance(ports, list)

    def test_check_db_permissions(self):
        scanner = SecurityScanner()
        issues = scanner.check_jarvis_db_permissions()
        assert isinstance(issues, list)

    def test_get_db_sizes(self):
        scanner = SecurityScanner()
        sizes = scanner.get_db_sizes()
        assert isinstance(sizes, dict)
        # At least some keys present
        assert "memory" in sizes

    def test_integrity_check_nonexistent(self):
        scanner = SecurityScanner()
        assert scanner.integrity_check("/nonexistent/path/to.db") is True

    def test_integrity_check_valid(self, tmp_path):
        import sqlite3
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.close()
        scanner = SecurityScanner()
        assert scanner.integrity_check(db_path) is True

    def test_hash_db_nonexistent(self):
        scanner = SecurityScanner()
        assert scanner.hash_db("/nonexistent.db") is None

    def test_hash_db_returns_hex(self, tmp_path):
        db_path = str(tmp_path / "hash_test.db")
        with open(db_path, "wb") as f:
            f.write(b"some data")
        scanner = SecurityScanner()
        h = scanner.hash_db(db_path)
        assert h is not None
        assert len(h) == 64  # SHA-256 hex

    def test_hash_db_changes_on_modification(self, tmp_path):
        db_path = str(tmp_path / "changing.db")
        with open(db_path, "wb") as f:
            f.write(b"version 1")
        scanner = SecurityScanner()
        h1 = scanner.hash_db(db_path)
        with open(db_path, "wb") as f:
            f.write(b"version 2")
        h2 = scanner.hash_db(db_path)
        assert h1 != h2
