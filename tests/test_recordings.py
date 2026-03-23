from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from echook_lora.protocol import DecodedPacket
from echook_lora.recordings import RecordingManager, to_epoch_ms


def encode_value(value: float) -> tuple[int, int]:
    if value == 0:
        return 0xFF, 0xFF
    if value > 127:
        hundreds = int(value // 100)
        remainder = int(value % 100)
        return 128 + hundreds, remainder or 0xFF
    integer_part = int(value)
    decimals = int(round((value - integer_part) * 100))
    return integer_part or 0xFF, decimals or 0xFF


def build_packet(packet_id: str, value: float, received_at: datetime, units: str = "") -> DecodedPacket:
    names = {
        "s": ("speed", "m/s"),
        "v": ("voltage", "V"),
        "i": ("current", "A"),
    }
    default_name, default_units = names.get(packet_id, (packet_id, units))
    data1, data2 = encode_value(value)
    return DecodedPacket(
        packet_id=packet_id,
        name=default_name,
        value=value,
        units=units or default_units,
        received_at=received_at,
        raw=bytes([123, ord(packet_id), data1, data2, 125]),
    )


class RecordingManagerTests(unittest.TestCase):
    def test_recording_lifecycle_produces_playback_state_and_laps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = RecordingManager(Path(tmp))
            started = manager.start_recording("Bench Run")
            self.assertTrue(started["is_recording"])

            base_time = datetime.now(timezone.utc)
            manager.record_packet(build_packet("s", 12.3, base_time))
            manager.record_packet(build_packet("v", 74.2, base_time + timedelta(seconds=1), "V"))
            manager.add_lap("Lap 1")
            stopped = manager.stop_recording()

            self.assertEqual(stopped["name"], "Bench Run")
            self.assertEqual(stopped["lap_count"], 1)
            recording_id = stopped["recording_id"]

            recordings = manager.recordings_snapshot()["recordings"]
            self.assertEqual(len(recordings), 1)
            self.assertEqual(recordings[0]["packet_count"], 2)

            playback = manager.playback_state(recording_id, cursor_ms=to_epoch_ms(base_time + timedelta(seconds=1)))
            self.assertEqual(playback["all_readings"]["s"]["value_display"], "12.3")
            self.assertEqual(playback["all_readings"]["v"]["value_display"], "74.2")
            self.assertEqual(playback["laps"][0]["label"], "Lap 1")

    def test_purge_oldest_removes_closed_recordings_when_quota_is_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = RecordingManager(Path(tmp))
            first = manager.start_recording("First")
            manager.record_packet(build_packet("s", 10.0, datetime.now(timezone.utc)))
            first_id = first["active_recording"]["recording_id"]
            manager.stop_recording()

            second = manager.start_recording("Second")
            manager.record_packet(build_packet("v", 50.0, datetime.now(timezone.utc)))
            second_id = second["active_recording"]["recording_id"]
            manager.stop_recording()

            recordings_before = manager.recordings_snapshot()["recordings"]
            single_recording_quota = max(item["size_bytes"] for item in recordings_before) + 1

            manager.update_settings(
                {
                    "recording_name_prefix": "Recording",
                    "recording_quota_bytes": single_recording_quota,
                    "reserved_free_bytes": 0,
                    "default_playback_speed": 1,
                }
            )

            deleted = manager.purge_oldest()
            remaining_ids = [item["recording_id"] for item in manager.recordings_snapshot()["recordings"]]

            self.assertIn(first_id, deleted)
            self.assertLess(len(remaining_ids), len(recordings_before))
            self.assertLessEqual(
                manager.storage_snapshot()["recordings_bytes"],
                manager.storage_snapshot()["recording_quota_bytes"],
            )


if __name__ == "__main__":
    unittest.main()
