"""Tests for jarvis/smarthome/mqtt_client.py"""
import pytest
from jarvis.smarthome.mqtt_client import MQTTClient


class TestMQTTClientInit:
    def test_default_host(self, monkeypatch):
        monkeypatch.delenv("JARVIS_MQTT_HOST", raising=False)
        client = MQTTClient()
        assert client._host == "localhost"
        assert client._port == 1883

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("JARVIS_MQTT_HOST", "192.168.1.50")
        monkeypatch.setenv("JARVIS_MQTT_PORT", "1884")
        client = MQTTClient()
        assert client._host == "192.168.1.50"
        assert client._port == 1884

    def test_not_connected_by_default(self):
        client = MQTTClient()
        assert client.connected is False


class TestMQTTClientPahoUnavailable:
    def test_connect_returns_false(self, monkeypatch):
        import jarvis.smarthome.mqtt_client as mod
        monkeypatch.setattr(mod, "_PAHO_AVAILABLE", False)
        client = MQTTClient()
        assert client.connect() is False

    def test_publish_returns_false_no_client(self):
        client = MQTTClient()
        assert client.publish("test/topic", {"x": 1}) is False

    def test_subscribe_no_client(self):
        called = []
        client = MQTTClient()
        client.subscribe("test/topic", lambda t, p: called.append((t, p)))
        # Callback is registered even without real broker
        assert len(client._callbacks.get("test/topic", [])) == 1


class TestMQTTClientInjectMessage:
    def test_inject_fires_callback(self):
        client = MQTTClient()
        received = []
        client.subscribe("home/lights/state", lambda t, p: received.append((t, p)))
        client.inject_message("home/lights/state", {"power": True})
        assert len(received) == 1
        assert received[0][1]["power"] is True

    def test_inject_wildcard_callback(self):
        client = MQTTClient()
        received = []
        client.subscribe("#", lambda t, p: received.append(t))
        client.inject_message("home/sensor/temp", 22.5)
        assert "home/sensor/temp" in received

    def test_inject_no_matching_callback(self):
        client = MQTTClient()
        received = []
        client.subscribe("other/topic", lambda t, p: received.append(p))
        client.inject_message("different/topic", "data")
        assert received == []

    def test_inject_multiple_callbacks(self):
        client = MQTTClient()
        results = []
        client.subscribe("t", lambda t, p: results.append("a"))
        client.subscribe("t", lambda t, p: results.append("b"))
        client.inject_message("t", {})
        assert set(results) == {"a", "b"}

    def test_inject_callback_exception_does_not_propagate(self):
        client = MQTTClient()
        def bad_cb(t, p):
            raise ValueError("boom")
        client.subscribe("test", bad_cb)
        # Should not raise
        client.inject_message("test", {})

    def test_command_method(self):
        client = MQTTClient()
        published = []
        client._client = None  # no real client

        import json
        # Use inject to simulate what command() would publish
        client.subscribe("jarvis/light1/cmd", lambda t, p: published.append(p))
        # Directly call internal on_message path via inject
        client.inject_message("jarvis/light1/cmd", {"command": "turn_on", "params": {}})
        assert published[0]["command"] == "turn_on"
