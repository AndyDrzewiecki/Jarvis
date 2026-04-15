"""
Device Registry — persistent SQLite store for registered smart home devices.

Every device known to Jarvis has a record here. The registry tracks:
  - Device identity (id, name, type, protocol, room)
  - Current state (power, brightness, temp, mode, …)
  - Online/offline status + last-seen timestamp

Environment variable:
  JARVIS_SMARTHOME_DB  — path to SQLite db (default: data/smarthome.db)
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from jarvis.smarthome.models import BaseDevice, DeviceState, DeviceStatus, DeviceType, Protocol

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "smarthome.db")


def _db_path() -> str:
    return os.environ.get("JARVIS_SMARTHOME_DB", _DEFAULT_DB)


@contextmanager
def _conn(path: str) -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


_CREATE_DEVICES = """
CREATE TABLE IF NOT EXISTS devices (
    device_id    TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    device_type  TEXT NOT NULL,
    protocol     TEXT NOT NULL,
    room         TEXT NOT NULL DEFAULT 'unknown',
    address      TEXT NOT NULL DEFAULT '',
    manufacturer TEXT NOT NULL DEFAULT '',
    model        TEXT NOT NULL DEFAULT '',
    adapter_type TEXT NOT NULL DEFAULT 'generic',
    status       TEXT NOT NULL DEFAULT 'unknown',
    state_json   TEXT NOT NULL DEFAULT '{}',
    capabilities TEXT NOT NULL DEFAULT '[]',
    metadata     TEXT NOT NULL DEFAULT '{}',
    registered_at TEXT NOT NULL,
    last_seen    TEXT
)
"""

_CREATE_SCENES = """
CREATE TABLE IF NOT EXISTS scenes (
    scene_name   TEXT PRIMARY KEY,
    actions_json TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL
)
"""


class DeviceRegistry:
    """Persistent registry for all smart home devices."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db = db_path or _db_path()
        self._init_db()

    def _init_db(self) -> None:
        with _conn(self._db) as con:
            con.execute(_CREATE_DEVICES)
            con.execute(_CREATE_SCENES)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def register(self, device: BaseDevice) -> BaseDevice:
        """Insert or replace a device record. Returns the device."""
        with _conn(self._db) as con:
            con.execute(
                """
                INSERT OR REPLACE INTO devices
                (device_id, display_name, device_type, protocol, room,
                 address, manufacturer, model, adapter_type, status,
                 state_json, capabilities, metadata, registered_at, last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    device.device_id,
                    device.display_name,
                    device.device_type.value,
                    device.protocol.value,
                    device.room,
                    device.address,
                    device.manufacturer,
                    device.model,
                    device.adapter_type,
                    device.status.value,
                    json.dumps(device.state.to_dict()),
                    json.dumps(device.capabilities),
                    json.dumps(device.metadata),
                    device.registered_at,
                    device.last_seen,
                ),
            )
        return device

    def get(self, device_id: str) -> Optional[BaseDevice]:
        """Return a device by ID, or None if not found."""
        with _conn(self._db) as con:
            row = con.execute(
                "SELECT * FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
        return self._row_to_device(row) if row else None

    def list_all(self) -> list[BaseDevice]:
        with _conn(self._db) as con:
            rows = con.execute("SELECT * FROM devices ORDER BY room, display_name").fetchall()
        return [self._row_to_device(r) for r in rows]

    def list_by_room(self, room: str) -> list[BaseDevice]:
        with _conn(self._db) as con:
            rows = con.execute(
                "SELECT * FROM devices WHERE room = ? ORDER BY display_name",
                (room.lower(),),
            ).fetchall()
        return [self._row_to_device(r) for r in rows]

    def list_by_type(self, device_type: DeviceType) -> list[BaseDevice]:
        with _conn(self._db) as con:
            rows = con.execute(
                "SELECT * FROM devices WHERE device_type = ? ORDER BY room, display_name",
                (device_type.value,),
            ).fetchall()
        return [self._row_to_device(r) for r in rows]

    def update_state(self, device_id: str, state: DeviceState) -> bool:
        """Update device state. Returns True if a row was updated."""
        now = datetime.now(timezone.utc).isoformat()
        with _conn(self._db) as con:
            cur = con.execute(
                "UPDATE devices SET state_json = ?, last_seen = ? WHERE device_id = ?",
                (json.dumps(state.to_dict()), now, device_id),
            )
        return cur.rowcount > 0

    def update_status(self, device_id: str, status: DeviceStatus) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with _conn(self._db) as con:
            cur = con.execute(
                "UPDATE devices SET status = ?, last_seen = ? WHERE device_id = ?",
                (status.value, now, device_id),
            )
        return cur.rowcount > 0

    def delete(self, device_id: str) -> bool:
        with _conn(self._db) as con:
            cur = con.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        with _conn(self._db) as con:
            return con.execute("SELECT COUNT(*) FROM devices").fetchone()[0]

    # ── Scenes ────────────────────────────────────────────────────────────────

    def save_scene(self, name: str, actions: list[dict]) -> None:
        """Persist a named scene (list of action dicts)."""
        now = datetime.now(timezone.utc).isoformat()
        with _conn(self._db) as con:
            con.execute(
                "INSERT OR REPLACE INTO scenes (scene_name, actions_json, created_at) VALUES (?,?,?)",
                (name.lower(), json.dumps(actions), now),
            )

    def get_scene(self, name: str) -> Optional[list[dict]]:
        with _conn(self._db) as con:
            row = con.execute(
                "SELECT actions_json FROM scenes WHERE scene_name = ?",
                (name.lower(),),
            ).fetchone()
        return json.loads(row["actions_json"]) if row else None

    def list_scenes(self) -> list[str]:
        with _conn(self._db) as con:
            rows = con.execute("SELECT scene_name FROM scenes ORDER BY scene_name").fetchall()
        return [r["scene_name"] for r in rows]

    def delete_scene(self, name: str) -> bool:
        with _conn(self._db) as con:
            cur = con.execute("DELETE FROM scenes WHERE scene_name = ?", (name.lower(),))
        return cur.rowcount > 0

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_device(row: sqlite3.Row) -> BaseDevice:
        return BaseDevice(
            device_id=row["device_id"],
            display_name=row["display_name"],
            device_type=DeviceType(row["device_type"]),
            protocol=Protocol(row["protocol"]),
            room=row["room"],
            address=row["address"],
            manufacturer=row["manufacturer"],
            model=row["model"],
            adapter_type=row["adapter_type"],
            status=DeviceStatus(row["status"]),
            state=DeviceState.from_dict(json.loads(row["state_json"])),
            capabilities=json.loads(row["capabilities"]),
            metadata=json.loads(row["metadata"]),
            registered_at=row["registered_at"],
            last_seen=row["last_seen"],
        )
