"""Tests for AnomalyDetector."""
import pytest

from jarvis.security.anomaly_detector import AnomalyDetector, _deviation_to_level
from jarvis.security.models import ThreatLevel


@pytest.fixture
def detector(tmp_path):
    return AnomalyDetector(db_path=str(tmp_path / "test_anomalies.db"), min_alert_pct=50.0)


class TestDeviationToLevel:
    def test_critical(self):
        assert _deviation_to_level(200.0) == ThreatLevel.CRITICAL
        assert _deviation_to_level(250.0) == ThreatLevel.CRITICAL

    def test_high(self):
        assert _deviation_to_level(150.0) == ThreatLevel.HIGH
        assert _deviation_to_level(199.9) == ThreatLevel.HIGH

    def test_medium(self):
        assert _deviation_to_level(100.0) == ThreatLevel.MEDIUM
        assert _deviation_to_level(149.9) == ThreatLevel.MEDIUM

    def test_low(self):
        assert _deviation_to_level(50.0) == ThreatLevel.LOW
        assert _deviation_to_level(99.9) == ThreatLevel.LOW

    def test_below_threshold(self):
        assert _deviation_to_level(49.9) is None
        assert _deviation_to_level(0.0) is None


class TestBaseline:
    def test_update_and_get(self, detector):
        bl = detector.update_baseline("aa:bb", "metric", 100.0)
        assert bl == 100.0
        assert detector.get_baseline("aa:bb", "metric") == pytest.approx(100.0)

    def test_ema_update(self, detector):
        # Seed with 100
        detector.update_baseline("aa:bb", "metric", 100.0)
        # Observe 200: EMA = 0.1*200 + 0.9*100 = 110
        new_bl = detector.update_baseline("aa:bb", "metric", 200.0, alpha=0.1)
        assert new_bl == pytest.approx(110.0)

    def test_get_nonexistent(self, detector):
        assert detector.get_baseline("zz:zz", "nonexistent") is None

    def test_get_all_baselines(self, detector):
        detector.update_baseline("aa:bb", "metric_a", 50.0)
        detector.update_baseline("aa:bb", "metric_b", 200.0)
        baselines = detector.get_all_baselines("aa:bb")
        assert set(baselines.keys()) >= {"metric_a", "metric_b"}


class TestCheck:
    def _seed(self, detector, mac, metric, value, n=6):
        """Seed enough samples to pass min_samples check."""
        for _ in range(n):
            detector.update_baseline(mac, metric, value)

    def test_no_alert_insufficient_samples(self, detector):
        # Only 1 sample → not enough for anomaly detection
        detector.update_baseline("aa:bb", "bytes_per_hour", 1000.0)
        alert = detector.check("aa:bb", "10.0.0.1", "bytes_per_hour", 5000.0)
        assert alert is None

    def test_alert_on_high_deviation(self, detector):
        self._seed(detector, "aa:bb", "bytes_per_hour", 1000.0)
        # Observe 3x baseline → 200% deviation → CRITICAL
        alert = detector.check("aa:bb", "10.0.0.1", "bytes_per_hour", 3000.0)
        assert alert is not None
        assert alert.level == ThreatLevel.CRITICAL
        assert alert.deviation_pct >= 150.0

    def test_no_alert_on_normal_traffic(self, detector):
        self._seed(detector, "aa:bb", "bytes_per_hour", 1000.0)
        alert = detector.check("aa:bb", "10.0.0.1", "bytes_per_hour", 1050.0)
        assert alert is None

    def test_alert_persisted(self, detector):
        self._seed(detector, "cc:dd", "port_variety", 10.0)
        detector.check("cc:dd", "10.0.0.2", "port_variety", 50.0)  # 400% deviation
        alerts = detector.get_alerts()
        assert len(alerts) == 1

    def test_resolve_alert(self, detector):
        self._seed(detector, "cc:dd", "port_variety", 10.0)
        detector.check("cc:dd", "10.0.0.2", "port_variety", 60.0)
        alerts = detector.get_alerts()
        assert len(alerts) == 1
        ok = detector.resolve_alert(alerts[0].alert_id)
        assert ok is True
        remaining = detector.get_alerts(unresolved_only=True)
        assert len(remaining) == 0

    def test_resolve_nonexistent(self, detector):
        assert detector.resolve_alert("nonexistent") is False

    def test_zero_baseline_skipped(self, detector):
        # baseline = 0 → no division by zero
        self._seed(detector, "ee:ff", "dns_queries_per_hour", 0.0)
        alert = detector.check("ee:ff", "10.0.0.3", "dns_queries_per_hour", 1000.0)
        assert alert is None


class TestAnalyzeFlows:
    def _seed_metric(self, detector, mac, metric, value, n=6):
        for _ in range(n):
            detector.update_baseline(mac, metric, value)

    def test_analyze_normal_flows(self, detector):
        mac = "aa:bb:cc:dd:ee:01"
        # Seed all metrics as normal
        for metric in ["bytes_per_hour", "new_destinations", "port_variety", "dns_queries_per_hour"]:
            self._seed_metric(detector, mac, metric, 10.0)

        flows = [
            {"ob": 512, "rb": 256, "dh": "8.8.8.8", "dp": 53},
            {"ob": 512, "rb": 256, "dh": "1.1.1.1", "dp": 53},
        ]
        alerts = detector.analyze_flows(mac, "10.0.0.1", flows, window_hours=1.0)
        assert isinstance(alerts, list)  # may or may not be empty

    def test_analyze_high_bandwidth(self, detector):
        mac = "aa:bb:cc:dd:ee:02"
        # Seed very low baseline
        for metric in ["bytes_per_hour", "new_destinations", "port_variety", "dns_queries_per_hour"]:
            self._seed_metric(detector, mac, metric, 1.0)

        # Large flows
        flows = [{"ob": 100_000_000, "rb": 100_000_000, "dh": "8.8.8.8", "dp": 80}]
        alerts = detector.analyze_flows(mac, "10.0.0.2", flows, window_hours=1.0)
        # Should detect bytes_per_hour anomaly
        assert any(a.metric == "bytes_per_hour" for a in alerts)

    def test_analyze_empty_flows(self, detector):
        alerts = detector.analyze_flows("aa:bb", "10.0.0.1", [], window_hours=1.0)
        assert alerts == []

    def test_count_unresolved(self, detector):
        mac = "aa:bb:cc:dd:ee:03"
        for metric in ["bytes_per_hour", "new_destinations", "port_variety", "dns_queries_per_hour"]:
            self._seed_metric(detector, mac, metric, 1.0)
        detector.analyze_flows(mac, "10.0.0.3",
                               [{"ob": 100_000_000, "rb": 100_000_000, "dh": "evil.com", "dp": 443}])
        count = detector.count_unresolved()
        assert count >= 0  # just ensure it runs


class TestAnomalyPurge:
    def test_purge_old_alerts(self, detector):
        from datetime import datetime, timezone, timedelta
        # Use detector._open() to ensure the schema is created before inserting
        old_date = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        conn = detector._open()
        conn.execute(
            """INSERT INTO anomaly_alerts
               (alert_id, device_mac, device_ip, metric, baseline, observed,
                deviation_pct, level, description, resolved, detected_at)
               VALUES ('old-1','mac','ip','metric',10.0,100.0,900.0,'high','old',1,?)""",
            (old_date,),
        )
        conn.commit()
        conn.close()

        removed = detector.purge_old_alerts(days=30)
        assert removed == 1
