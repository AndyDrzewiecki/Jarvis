"""Tests for ArubaClient."""
import pytest
from unittest.mock import MagicMock

from jarvis.security.aruba_client import ArubaClient


def _authed_session(json_return=None):
    """Session that pretends auth succeeded and returns json on GET/POST."""
    sess = MagicMock()
    login_resp = MagicMock()
    login_resp.status_code = 200
    login_resp.json.return_value = {"_global_result": {"X-CSRF-Token": "csrf123"}}

    data_resp = MagicMock()
    data_resp.status_code = 200
    data_resp.json.return_value = json_return if json_return is not None else []

    # First POST = login, subsequent = data
    sess.post.side_effect = [login_resp, data_resp, data_resp, data_resp]
    sess.get.return_value = data_resp
    return sess


class TestArubaClientConfigured:
    def _client(self, json_return=None):
        sess = _authed_session(json_return)
        c = ArubaClient(
            base_url="http://aruba.local:4343",
            username="admin",
            password="secret",
            _session=sess,
        )
        c._token = "csrf123"   # Pre-set token to skip login in tests
        return c

    def test_configured_true(self):
        c = self._client()
        assert c.configured is True

    def test_unconfigured(self):
        c = ArubaClient(base_url="", password="")
        assert c.configured is False

    def test_get_clients_list(self):
        clients = [{"mac": "aa:bb:cc", "ip": "192.168.1.5", "ssid": "JarvisMain"}]
        c = self._client(clients)
        result = c.get_clients()
        assert result == clients

    def test_get_clients_wrapped(self):
        payload = {"_data": [{"mac": "x", "ssid": "y"}]}
        c = self._client(payload)
        result = c.get_clients()
        assert result == payload["_data"]

    def test_get_aps(self):
        aps = [{"name": "AP-Living", "ip": "192.168.1.2", "model": "AP-505"}]
        c = self._client(aps)
        result = c.get_aps()
        assert result == aps

    def test_get_rogue_aps(self):
        rogues = [{"ssid": "EvilNet", "bssid": "ff:ff:ff:ff:ff:ff", "classification": "rogue"}]
        c = self._client(rogues)
        result = c.get_rogue_aps()
        assert result == rogues

    def test_get_ssids(self):
        ssids = [{"name": "JarvisMain", "vlan": 10}]
        c = self._client(ssids)
        result = c.get_ssids()
        assert result == ssids

    def test_disconnect_client(self):
        sess = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "ok"}
        sess.post.return_value = resp
        c = ArubaClient(base_url="http://aruba.local", password="x", _session=sess)
        c._token = "tok"
        assert c.disconnect_client("aa:bb:cc") is True

    def test_blacklist_client(self):
        sess = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "ok"}
        sess.post.return_value = resp
        c = ArubaClient(base_url="http://aruba.local", password="x", _session=sess)
        c._token = "tok"
        assert c.blacklist_client("aa:bb:cc", "test reason") is True

    def test_move_client_to_vlan(self):
        sess = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "ok"}
        sess.post.return_value = resp
        c = ArubaClient(base_url="http://aruba.local", password="x", _session=sess)
        c._token = "tok"
        assert c.move_client_to_vlan("aa:bb:cc", 99) is True

    def test_get_client_count(self):
        clients = [
            {"mac": "a", "ssid": "Main"},
            {"mac": "b", "ssid": "Main"},
            {"mac": "c", "ssid": "Guest"},
        ]
        c = self._client(clients)
        counts = c.get_client_count()
        assert counts["Main"] == 2
        assert counts["Guest"] == 1


class TestArubaClientUnconfigured:
    def _client(self):
        return ArubaClient(base_url="", password="")

    def test_get_clients_empty(self):
        assert self._client().get_clients() == []

    def test_get_aps_empty(self):
        assert self._client().get_aps() == []

    def test_get_rogue_aps_empty(self):
        assert self._client().get_rogue_aps() == []

    def test_disconnect_client_false(self):
        assert self._client().disconnect_client("x") is False


class TestArubaClientErrors:
    def test_get_returns_empty_on_exception(self):
        sess = MagicMock()
        sess.get.side_effect = Exception("refused")
        c = ArubaClient(base_url="http://aruba.local", password="x", _session=sess)
        c._token = "tok"
        assert c.get_clients() == []

    def test_auth_failure_returns_false(self):
        sess = MagicMock()
        sess.post.side_effect = Exception("auth failed")
        c = ArubaClient(base_url="http://aruba.local", password="x", _session=sess)
        assert c._ensure_auth() is False
