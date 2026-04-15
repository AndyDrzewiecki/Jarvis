"""
MQTT Client — lightweight wrapper around paho-mqtt for IoT device control.

Provides:
  - Pub/sub with per-topic callbacks
  - Device command publishing
  - Graceful degradation when paho-mqtt is not installed

Environment variables:
  JARVIS_MQTT_HOST   — broker host (default: localhost)
  JARVIS_MQTT_PORT   — broker port (default: 1883)
  JARVIS_MQTT_USER   — username (optional)
  JARVIS_MQTT_PASS   — password (optional)
  JARVIS_MQTT_TLS    — "true" to enable TLS (default: false)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt  # type: ignore[import-untyped]
    _PAHO_AVAILABLE = True
except ImportError:
    mqtt = None  # type: ignore[assignment]
    _PAHO_AVAILABLE = False

MessageCallback = Callable[[str, Any], None]   # (topic, payload) -> None


class MQTTClient:
    """
    Thin MQTT wrapper that routes incoming messages to registered callbacks.
    Degrades gracefully when paho-mqtt is absent.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: str = "jarvis-smarthome",
    ) -> None:
        self._host = host or os.environ.get("JARVIS_MQTT_HOST", "localhost")
        self._port = port or int(os.environ.get("JARVIS_MQTT_PORT", "1883"))
        self._username = username or os.environ.get("JARVIS_MQTT_USER")
        self._password = password or os.environ.get("JARVIS_MQTT_PASS")
        self._tls = os.environ.get("JARVIS_MQTT_TLS", "false").lower() in ("true", "1")
        self._client_id = client_id
        self._callbacks: dict[str, list[MessageCallback]] = {}
        self._client: Any = None
        self._connected = False
        self._lock = threading.Lock()

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to the MQTT broker. Returns True on success."""
        if not _PAHO_AVAILABLE:
            logger.warning("paho-mqtt not installed — MQTT unavailable")
            return False
        try:
            client = mqtt.Client(client_id=self._client_id, clean_session=True)
            if self._username:
                client.username_pw_set(self._username, self._password)
            if self._tls:
                client.tls_set()
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            client.connect(self._host, self._port, keepalive=60)
            client.loop_start()
            with self._lock:
                self._client = client
            return True
        except Exception as exc:
            logger.error("MQTT connect error: %s", exc)
            return False

    def disconnect(self) -> None:
        with self._lock:
            if self._client is not None:
                try:
                    self._client.loop_stop()
                    self._client.disconnect()
                except Exception:
                    pass
                self._client = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def paho_available(self) -> bool:
        return _PAHO_AVAILABLE

    # ── Pub/Sub ───────────────────────────────────────────────────────────────

    def subscribe(self, topic: str, callback: MessageCallback) -> bool:
        """Subscribe to a topic and register a callback."""
        with self._lock:
            self._callbacks.setdefault(topic, []).append(callback)
            if self._client and self._connected:
                self._client.subscribe(topic)
                return True
        return False

    def publish(self, topic: str, payload: Any, qos: int = 0, retain: bool = False) -> bool:
        """Publish a message. Payload is JSON-serialised if not str/bytes."""
        if isinstance(payload, (str, bytes)):
            raw = payload
        else:
            raw = json.dumps(payload)
        with self._lock:
            if self._client is None:
                logger.debug("MQTT publish skipped (not connected): %s %s", topic, raw)
                return False
            try:
                self._client.publish(topic, raw, qos=qos, retain=retain)
                return True
            except Exception as exc:
                logger.error("MQTT publish error on %s: %s", topic, exc)
                return False

    def command(self, device_topic_prefix: str, command: str, params: Optional[dict] = None) -> bool:
        """
        Send a device command.
        Publishes to  <prefix>/cmd  with {"command": cmd, "params": {...}}
        """
        topic = f"{device_topic_prefix}/cmd"
        payload = {"command": command, "params": params or {}}
        return self.publish(topic, payload)

    # ── Internal callbacks ────────────────────────────────────────────────────

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        if rc == 0:
            self._connected = True
            logger.info("MQTT connected to %s:%s", self._host, self._port)
            # Re-subscribe after reconnect
            with self._lock:
                for topic in self._callbacks:
                    client.subscribe(topic)
        else:
            logger.warning("MQTT connect failed, rc=%s", rc)

    def _on_disconnect(self, client: Any, userdata: Any, rc: int) -> None:
        self._connected = False
        if rc != 0:
            logger.warning("MQTT unexpected disconnect, rc=%s", rc)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = msg.payload.decode(errors="replace")

        callbacks = []
        with self._lock:
            # Exact match
            if topic in self._callbacks:
                callbacks.extend(self._callbacks[topic])
            # Wildcard: '#' subscribers
            if "#" in self._callbacks:
                callbacks.extend(self._callbacks["#"])

        for cb in callbacks:
            try:
                cb(topic, payload)
            except Exception as exc:
                logger.error("MQTT callback error for %s: %s", topic, exc)

    # ── Testing helper ────────────────────────────────────────────────────────

    def inject_message(self, topic: str, payload: Any) -> None:
        """
        Inject a simulated message — for testing without a real broker.
        Fires all registered callbacks for the topic.
        """
        callbacks = []
        with self._lock:
            if topic in self._callbacks:
                callbacks.extend(self._callbacks[topic])
            if "#" in self._callbacks:
                callbacks.extend(self._callbacks["#"])
        for cb in callbacks:
            try:
                cb(topic, payload)
            except Exception as exc:
                logger.error("inject_message callback error: %s", exc)
