"""Tests for FirewallaClient."""
import pytest
from unittest.mock import MagicMock, patch

from jarvis.security.firewalla_client import FirewallaClient


def _mock_session(json_return):
    """Create a mock requests Session that returns json_return on .get()/.post()."""
    sess = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = json_return
    sess.get.return_value  = resp
    sess.post.return_value = resp
    sess.delete.return_value = resp
    return sess


class TestFirewallaClientConfigured:
    def _client(self, json_return=None):
        sess = _mock_session(json_return or [])
        return FirewallaClient(base_url="http://fw.local:8833", token="tok123", _session=sess)

    def test_configured_true(self):
        c = self._client()
        assert c.configured is True

    def test_unconfigured(self):
        c = FirewallaClient(base_url="", token="")
        assert c.configured is False

    def test_get_devices_list(self):
        devices = [{"mac": "aa:bb", "ip": "192.168.1.1", "online": True}]
        c = self._client(devices)
        result = c.get_devices()
        assert result == devices

    def test_get_devices_wrapped(self):
        payload = {"devices": [{"mac": "x", "ip": "y"}]}
        c = self._client(payload)
        result = c.get_devices()
        assert result == payload["devices"]

    def test_get_flows(self):
        flows = [{"sh": "192.168.1.1", "dh": "8.8.8.8", "ob": 1024, "rb": 512}]
        c = self._client(flows)
        result = c.get_flows(limit=10, hours=1)
        assert result == flows

    def test_get_alarms(self):
        alarms = [{"aid": "1", "type": "ALARM_SCAN", "severity": "2"}]
        c = self._client({"alarms": alarms})
        result = c.get_alarms()
        assert result == alarms

    def test_create_block_rule(self):
        sess = _mock_session({"id": "rule-abc123"})
        c = FirewallaClient(base_url="http://fw.local:8833", token="tok", _session=sess)
        rule_id = c.create_block_rule("1.2.3.4", target_type="ip", reason="test")
        assert rule_id == "rule-abc123"
        sess.post.assert_called_once()

    def test_delete_rule(self):
        sess = _mock_session({})
        c = FirewallaClient(base_url="http://fw.local:8833", token="tok", _session=sess)
        result = c.delete_rule("rule-abc123")
        assert result is True
        sess.delete.assert_called_once()

    def test_get_stats(self):
        stats = {"bytes_in": 1000000, "bytes_out": 500000}
        c = self._client(stats)
        result = c.get_stats()
        assert result == stats

    def test_get_rules(self):
        rules = [{"id": "r1", "action": "block", "target": "bad.com"}]
        c = self._client({"rules": rules})
        result = c.get_rules()
        assert result == rules


class TestFirewallaClientUnconfigured:
    def _client(self):
        return FirewallaClient(base_url="", token="")

    def test_get_devices_returns_empty(self):
        assert self._client().get_devices() == []

    def test_get_flows_returns_empty(self):
        assert self._client().get_flows() == []

    def test_get_alarms_returns_empty(self):
        assert self._client().get_alarms() == []

    def test_create_block_rule_returns_none(self):
        assert self._client().create_block_rule("1.2.3.4") is None

    def test_delete_rule_returns_false(self):
        assert self._client().delete_rule("x") is False

    def test_get_stats_returns_empty(self):
        assert self._client().get_stats() == {}


class TestFirewallaClientErrors:
    def test_get_returns_empty_on_exception(self):
        sess = MagicMock()
        sess.get.side_effect = Exception("connection refused")
        c = FirewallaClient(base_url="http://fw.local", token="tok", _session=sess)
        assert c.get_devices() == []

    def test_post_returns_none_on_exception(self):
        sess = MagicMock()
        sess.post.side_effect = Exception("timeout")
        c = FirewallaClient(base_url="http://fw.local", token="tok", _session=sess)
        assert c.create_block_rule("x") is None

    def test_delete_returns_false_on_exception(self):
        sess = MagicMock()
        sess.delete.side_effect = Exception("timeout")
        c = FirewallaClient(base_url="http://fw.local", token="tok", _session=sess)
        assert c.delete_rule("x") is False

    def test_resolve_alarm(self):
        sess = _mock_session({"status": "ok"})
        c = FirewallaClient(base_url="http://fw.local", token="tok", _session=sess)
        assert c.resolve_alarm("alarm-1") is True

    def test_get_target_lists(self):
        sess = _mock_session({"target_lists": [{"id": "tl1"}]})
        c = FirewallaClient(base_url="http://fw.local", token="tok", _session=sess)
        result = c.get_target_lists()
        assert result == [{"id": "tl1"}]

    def test_add_to_target_list(self):
        sess = _mock_session({"ok": True})
        c = FirewallaClient(base_url="http://fw.local", token="tok", _session=sess)
        assert c.add_to_target_list("tl1", ["1.2.3.4"]) is True
