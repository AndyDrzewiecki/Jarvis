"""Tests for jarvis/smarthome/registry.py"""
import os
import pytest
from jarvis.smarthome.models import (
    BaseDevice, DeviceType, Protocol, DeviceStatus, DeviceState,
)
from jarvis.smarthome.registry import DeviceRegistry


@pytest.fixture
def registry(tmp_path):
    db = str(tmp_path / "test_smarthome.db")
    os.environ["JARVIS_SMARTHOME_DB"] = db
    reg = DeviceRegistry(db_path=db)
    yield reg
    os.environ.pop("JARVIS_SMARTHOME_DB", None)


def _light(room="kitchen", name="Kitchen Light"):
    return BaseDevice.new(
        display_name=name,
        device_type=DeviceType.LIGHT,
        protocol=Protocol.BLE,
        room=room,
        adapter_type="hubspace",
    )


def _tv(room="living room"):
    return BaseDevice.new(
        display_name="Living Room TV",
        device_type=DeviceType.TV,
        protocol=Protocol.CEC,
        room=room,
        adapter_type="tv",
    )


class TestRegistryBasicCRUD:
    def test_register_and_get(self, registry):
        dev = _light()
        registry.register(dev)
        retrieved = registry.get(dev.device_id)
        assert retrieved is not None
        assert retrieved.device_id == dev.device_id
        assert retrieved.display_name == "Kitchen Light"

    def test_get_nonexistent(self, registry):
        assert registry.get("no-such-id") is None

    def test_list_all_empty(self, registry):
        assert registry.list_all() == []

    def test_list_all(self, registry):
        d1, d2 = _light("kitchen"), _tv("living room")
        registry.register(d1)
        registry.register(d2)
        all_devs = registry.list_all()
        assert len(all_devs) == 2

    def test_count(self, registry):
        assert registry.count() == 0
        registry.register(_light())
        assert registry.count() == 1
        registry.register(_tv())
        assert registry.count() == 2

    def test_delete(self, registry):
        dev = _light()
        registry.register(dev)
        assert registry.get(dev.device_id) is not None
        result = registry.delete(dev.device_id)
        assert result is True
        assert registry.get(dev.device_id) is None

    def test_delete_nonexistent(self, registry):
        assert registry.delete("ghost") is False

    def test_register_upsert(self, registry):
        dev = _light()
        registry.register(dev)
        dev.display_name = "Updated Name"
        registry.register(dev)
        retrieved = registry.get(dev.device_id)
        assert retrieved.display_name == "Updated Name"
        assert registry.count() == 1


class TestRegistryFilters:
    def test_list_by_room(self, registry):
        registry.register(_light("kitchen"))
        registry.register(_light("bedroom"))
        registry.register(_tv("living room"))

        kitchen = registry.list_by_room("kitchen")
        assert len(kitchen) == 1
        assert kitchen[0].room == "kitchen"

    def test_list_by_room_empty(self, registry):
        registry.register(_light("kitchen"))
        assert registry.list_by_room("bathroom") == []

    def test_list_by_type(self, registry):
        registry.register(_light())
        registry.register(_light())
        registry.register(_tv())
        lights = registry.list_by_type(DeviceType.LIGHT)
        assert len(lights) == 2
        tvs = registry.list_by_type(DeviceType.TV)
        assert len(tvs) == 1


class TestRegistryStateUpdates:
    def test_update_state(self, registry):
        dev = _light()
        registry.register(dev)
        new_state = DeviceState(power=True, brightness=80)
        result = registry.update_state(dev.device_id, new_state)
        assert result is True
        retrieved = registry.get(dev.device_id)
        assert retrieved.state.power is True
        assert retrieved.state.brightness == 80

    def test_update_state_nonexistent(self, registry):
        result = registry.update_state("ghost", DeviceState())
        assert result is False

    def test_update_status(self, registry):
        dev = _light()
        registry.register(dev)
        result = registry.update_status(dev.device_id, DeviceStatus.ONLINE)
        assert result is True
        retrieved = registry.get(dev.device_id)
        assert retrieved.status == DeviceStatus.ONLINE

    def test_update_status_nonexistent(self, registry):
        assert registry.update_status("ghost", DeviceStatus.ONLINE) is False


class TestRegistryScenes:
    def test_save_and_get_scene(self, registry):
        actions = [{"action_type": "device_command", "device_id": "d1", "command": "turn_off"}]
        registry.save_scene("goodnight", actions)
        retrieved = registry.get_scene("goodnight")
        assert retrieved is not None
        assert len(retrieved) == 1

    def test_get_scene_not_found(self, registry):
        assert registry.get_scene("nonexistent") is None

    def test_list_scenes(self, registry):
        registry.save_scene("goodnight", [])
        registry.save_scene("morning", [])
        scenes = registry.list_scenes()
        assert "goodnight" in scenes
        assert "morning" in scenes

    def test_delete_scene(self, registry):
        registry.save_scene("temp", [])
        assert registry.delete_scene("temp") is True
        assert registry.get_scene("temp") is None

    def test_delete_scene_not_found(self, registry):
        assert registry.delete_scene("ghost") is False

    def test_scene_name_normalized_lowercase(self, registry):
        registry.save_scene("GoodNight", [{"x": 1}])
        assert registry.get_scene("goodnight") is not None

    def test_upsert_scene(self, registry):
        registry.save_scene("test", [{"a": 1}])
        registry.save_scene("test", [{"a": 1}, {"b": 2}])
        result = registry.get_scene("test")
        assert len(result) == 2


class TestDeviceStatePersistence:
    def test_state_survives_reload(self, tmp_path):
        db = str(tmp_path / "persist.db")
        reg = DeviceRegistry(db_path=db)
        dev = _light()
        reg.register(dev)
        reg.update_state(dev.device_id, DeviceState(power=True, brightness=60))

        reg2 = DeviceRegistry(db_path=db)
        retrieved = reg2.get(dev.device_id)
        assert retrieved.state.power is True
        assert retrieved.state.brightness == 60
