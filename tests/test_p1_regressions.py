import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.audio.linux.bluetooth import BluetoothDeviceDatabase
from src.audio.linux.pipewire import PipeWireBackend
from src.audio.linux.pulseaudio import PulseAudioBackend
from src.audio.microphone import Microphone
from src.audio.linux.discovery_monitor import BluetoothDiscoveryMonitor


class BluetoothDatabaseTests(unittest.TestCase):
    def test_mac_is_identity_and_name_change_does_not_create_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            database = BluetoothDeviceDatabase(Path(directory) / "devices.json")
            database.upsert("Old name", "AA:BB:CC:DD:EE:FF", True)
            self.assertTrue(database.get("Renamed", "AA:BB:CC:DD:EE:FF")["input_capable"])
            database.upsert("Renamed", "AA:BB:CC:DD:EE:FF", True)
            records = database.all()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["name"], "Renamed")

    def test_same_name_different_mac_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            database = BluetoothDeviceDatabase(Path(directory) / "devices.json")
            database.upsert("Headset", "AA:BB:CC:DD:EE:01", True)
            database.upsert("Headset", "AA:BB:CC:DD:EE:02", False)
            self.assertEqual(len(database.all()), 2)

    def test_corrupt_json_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.json"
            path.write_text("{bad json", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                BluetoothDeviceDatabase(path).all()


class PassiveEnumerationTests(unittest.TestCase):
    def test_pipewire_listing_does_not_probe(self):
        backend = PipeWireBackend()
        backend._get_status = Mock(return_value="Sources:\n  * 42. Built-in Mic [vol: 1.00]\n")
        backend._cached_bluetooth_microphones = Mock(return_value=[])
        backend._discover_bluetooth_microphones = Mock(side_effect=AssertionError("probe called"))
        result = backend.list_microphones()
        self.assertEqual([item.name for item in result], ["Built-in Mic"])
        backend._discover_bluetooth_microphones.assert_not_called()

    def test_pulseaudio_listing_does_not_probe(self):
        backend = PulseAudioBackend()
        backend._run_pactl = Mock(return_value="1\talsa_input.test\tmodule\n")
        backend._cached_bluetooth_microphones = Mock(return_value=[])
        backend._discover_bluetooth_microphones = Mock(side_effect=AssertionError("probe called"))
        result = backend.list_microphones()
        self.assertEqual([item.name for item in result], ["alsa_input.test"])
        backend._discover_bluetooth_microphones.assert_not_called()

    def test_transient_probe_failure_is_not_cached(self):
        backend = PipeWireBackend()
        backend._get_default_source = Mock(return_value="alsa_input.default")
        backend._set_bluetooth_profile = Mock()
        backend._wait_for_bluetooth_source = Mock(side_effect=TimeoutError("temporary timeout"))
        backend._restore_probe_state = Mock(return_value=[])
        backend._bluetooth_db = Mock()
        card = {"name": "bluez_card.AA_BB_CC_DD_EE_FF", "description": "Headset", "active_profile": "a2dp_sink", "profiles": ["handsfree_head_unit"]}
        with self.assertRaisesRegex(RuntimeError, "inconclusive"):
            backend._probe_bluetooth_device(card, "AA:BB:CC:DD:EE:FF")
        backend._bluetooth_db.upsert.assert_not_called()

    def test_pipewire_recording_rejects_second_start(self):
        backend = PipeWireBackend()
        backend._recording_process = Mock()
        microphone = Microphone(id="1", name="Mic", backend_data={"node_id": 1})
        with self.assertRaisesRegex(RuntimeError, "already active"):
            backend.start_recording(microphone, Path("unused.wav"))

    def test_pulseaudio_recording_rejects_second_start(self):
        backend = PulseAudioBackend()
        backend._recording_process = Mock()
        microphone = Microphone(
            id="1", name="Mic", backend_data={"source_name": "alsa_input.test"}
        )
        with self.assertRaisesRegex(RuntimeError, "already active"):
            backend.start_recording(microphone, Path("unused.wav"))

    def test_pulseaudio_restores_source_even_if_profile_restore_fails(self):
        backend = PulseAudioBackend()
        backend._set_bluetooth_profile = Mock(side_effect=RuntimeError("profile failure"))
        backend._wait_for_source = Mock(return_value="alsa_input.original")
        backend._set_default_source = Mock()
        with self.assertRaisesRegex(RuntimeError, "fully restore"):
            backend._restore_bluetooth_state(
                "bluez_card.test", "a2dp_sink", "alsa_input.original"
            )
        backend._wait_for_source.assert_called_once_with("alsa_input.original")
        backend._set_default_source.assert_called_once_with("alsa_input.original")


class DiscoveryMonitorTests(unittest.TestCase):
    def test_monitor_does_not_discover_during_recording(self):
        backend = Mock()
        monitor = BluetoothDiscoveryMonitor(backend=backend, interval=0.5)
        monitor.begin_recording()
        monitor._run_once()
        backend.discover_bluetooth_devices.assert_not_called()


if __name__ == "__main__":
    unittest.main()
