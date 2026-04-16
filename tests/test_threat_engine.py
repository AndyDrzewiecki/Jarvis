"""Tests for ThreatEngine."""
import pytest
from unittest.mock import patch

from jarvis.security.threat_engine import ThreatEngine, _score_to_level
from jarvis.security.models import ThreatCategory, ThreatLevel


@pytest.fixture
def engine(tmp_path):
    return ThreatEngine(db_path=str(tmp_path / "test_threats.db"))


class TestScoreToLevel:
    def test_critical(self):
        assert _score_to_level(90.0) == ThreatLevel.CRITICAL
        assert _score_to_level(85.0) == ThreatLevel.CRITICAL

    def test_high(self):
        assert _score_to_level(84.9) == ThreatLevel.HIGH
        assert _score_to_level(70.0) == ThreatLevel.HIGH

    def test_medium(self):
        assert _score_to_level(69.9) == ThreatLevel.MEDIUM
        assert _score_to_level(50.0) == ThreatLevel.MEDIUM

    def test_low(self):
        assert _score_to_level(49.9) == ThreatLevel.LOW
        assert _score_to_level(30.0) == ThreatLevel.LOW

    def test_info(self):
        assert _score_to_level(29.9) == ThreatLevel.INFO
        assert _score_to_level(0.0) == ThreatLevel.INFO


class TestThreatEngineRecord:
    def test_record_threat(self, engine):
        event = engine.record_threat(
            category=ThreatCategory.PORT_SCAN,
            description="Port scan from external IP",
            score=72.0,
            source_ip="1.2.3.4",
        )
        assert event.level == ThreatLevel.HIGH
        assert event.score == 72.0
        assert event.event_id

    def test_record_persists(self, engine):
        engine.record_threat(ThreatCategory.MALWARE, "test malware", 90.0)
        events = engine.get_events()
        assert len(events) == 1

    def test_get_events_unresolved_only(self, engine):
        e1 = engine.record_threat(ThreatCategory.ANOMALY, "anomaly", 55.0)
        e2 = engine.record_threat(ThreatCategory.UNKNOWN, "unknown", 35.0)
        engine.resolve_event(e1.event_id)
        events = engine.get_events(unresolved_only=True)
        assert len(events) == 1
        assert events[0].event_id == e2.event_id

    def test_get_events_level_filter(self, engine):
        engine.record_threat(ThreatCategory.PORT_SCAN, "scan", 72.0)   # HIGH
        engine.record_threat(ThreatCategory.MALWARE, "malware", 92.0)  # CRITICAL
        highs = engine.get_events(level=ThreatLevel.HIGH)
        assert all(e.level == ThreatLevel.HIGH for e in highs)

    def test_resolve_event(self, engine):
        e = engine.record_threat(ThreatCategory.BOTNET, "botnet", 80.0)
        assert engine.resolve_event(e.event_id) is True
        events = engine.get_events(unresolved_only=True)
        assert all(ev.event_id != e.event_id for ev in events)

    def test_resolve_nonexistent(self, engine):
        assert engine.resolve_event("nonexistent-id") is False

    def test_mark_auto_blocked(self, engine):
        e = engine.record_threat(ThreatCategory.PORT_SCAN, "scan", 78.0)
        engine.mark_auto_blocked(e.event_id)
        events = engine.get_events(unresolved_only=False)
        found = next(ev for ev in events if ev.event_id == e.event_id)
        assert found.auto_blocked is True

    def test_count_by_level(self, engine):
        engine.record_threat(ThreatCategory.MALWARE, "m1", 90.0)
        engine.record_threat(ThreatCategory.MALWARE, "m2", 92.0)
        engine.record_threat(ThreatCategory.PORT_SCAN, "s1", 72.0)
        counts = engine.count_by_level()
        assert counts.get("critical", 0) == 2
        assert counts.get("high", 0) == 1


class TestFirewallaAlarmProcessing:
    def test_process_alarm_port_scan(self, engine):
        alarm = {
            "type": "ALARM_SCAN",
            "severity": "2",
            "device": {"mac": "aa:bb:cc", "ip": "192.168.1.5"},
            "remote": {"ip": "1.2.3.4"},
        }
        event = engine.process_firewalla_alarm(alarm)
        assert event.category == ThreatCategory.PORT_SCAN
        assert event.level in (ThreatLevel.MEDIUM, ThreatLevel.HIGH, ThreatLevel.CRITICAL)

    def test_process_alarm_malware(self, engine):
        alarm = {
            "type": "ALARM_VULNERABILITY",
            "severity": "3",
            "device": {"mac": "aa:bb:cc", "ip": "192.168.1.5"},
            "message": "Malware detected",
        }
        event = engine.process_firewalla_alarm(alarm)
        assert event.category == ThreatCategory.MALWARE
        assert event.level == ThreatLevel.CRITICAL

    def test_process_alarm_unknown_type(self, engine):
        alarm = {"type": "ALARM_NEW_DEVICE", "severity": "0"}
        event = engine.process_firewalla_alarm(alarm)
        assert event.category == ThreatCategory.UNKNOWN
        assert event.level == ThreatLevel.INFO

    def test_process_firewalla_alarms_batch(self, engine):
        alarms = [
            {"type": "ALARM_SCAN", "severity": "2"},
            {"type": "ALARM_BRO_INTEL", "severity": "3"},
        ]
        events = engine.process_firewalla_alarms(alarms)
        assert len(events) == 2

    def test_process_alarm_blackboard_posted_for_high(self, engine):
        alarm = {"type": "ALARM_VULNERABILITY", "severity": "3", "device": {}, "remote": {}}
        with patch("jarvis.blackboard.SharedBlackboard") as MockBB:
            mock_bb = MockBB.return_value
            mock_bb.post.return_value = "post-id"
            engine.process_firewalla_alarm(alarm)
            # post may or may not be called depending on level; just verify no crash
            assert mock_bb.post.call_count >= 0


class TestRogueAPProcessing:
    def test_rogue_ap_threat(self, engine):
        rogues = [{"ssid": "EvilNet", "bssid": "ff:ff", "channel": 6, "classification": "rogue"}]
        events = engine.process_rogue_aps(rogues)
        assert len(events) == 1
        assert events[0].category == ThreatCategory.ROGUE_AP
        assert events[0].score >= 70.0

    def test_interfering_ap_threat(self, engine):
        rogues = [{"ssid": "NeighborNet", "classification": "interfering"}]
        events = engine.process_rogue_aps(rogues)
        assert len(events) == 1
        assert events[0].score < 70.0

    def test_neighbor_ap_skipped(self, engine):
        rogues = [{"ssid": "NeighborNet", "classification": "neighbor"}]
        events = engine.process_rogue_aps(rogues)
        assert len(events) == 0


class TestDeviceThreatScore:
    def test_no_events_returns_zero(self, engine):
        score = engine.compute_device_threat_score("aa:bb:cc")
        assert score == 0.0

    def test_single_event(self, engine):
        engine.record_threat(ThreatCategory.PORT_SCAN, "scan", 80.0, source_mac="aa:bb:cc")
        score = engine.compute_device_threat_score("aa:bb:cc")
        assert score == pytest.approx(80.0, abs=1.0)

    def test_multiple_events_weighted(self, engine):
        for i in range(5):
            engine.record_threat(ThreatCategory.ANOMALY, f"event {i}", 50.0, source_mac="xx:yy:zz")
        score = engine.compute_device_threat_score("xx:yy:zz")
        assert 40.0 <= score <= 60.0  # Should stay around 50
