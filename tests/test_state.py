from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from echook_lora.protocol import DecodedPacket
from echook_lora.state import TelemetryStore


def build_packet(packet_id: str, name: str, value: float, units: str, received_at: datetime) -> DecodedPacket:
    return DecodedPacket(
        packet_id=packet_id,
        name=name,
        value=value,
        units=units,
        received_at=received_at,
        raw=bytes([123, ord(packet_id), 1, 2, 125]),
    )


class TelemetryStoreTests(unittest.TestCase):
    def test_snapshot_reports_waiting_before_packets_arrive(self) -> None:
        snapshot = TelemetryStore().snapshot()

        self.assertEqual(snapshot["connection_status"], "waiting")
        self.assertEqual(snapshot["latest_update_display"], "Waiting for packets")
        self.assertEqual(snapshot["packet_age_display"], "Waiting for packets")
        self.assertEqual(snapshot["recent_history"]["s"], [])

    def test_snapshot_formats_display_fields_and_bounds_history(self) -> None:
        store = TelemetryStore(recent_history_limit=2)
        base_time = datetime.now(timezone.utc) - timedelta(seconds=3)

        store.update(build_packet("s", "speed", 12.3, "m/s", base_time))
        store.update(build_packet("s", "speed", 18.0, "m/s", base_time + timedelta(seconds=1)))
        store.update(build_packet("s", "speed", 21.25, "m/s", base_time + timedelta(seconds=2)))
        store.update(build_packet("a", "temp1", 46.0, "C", base_time + timedelta(seconds=2)))

        snapshot = store.snapshot()
        speed = snapshot["primary"]["s"]
        temp = snapshot["primary"]["a"]
        speed_history = snapshot["recent_history"]["s"]

        self.assertEqual(snapshot["connection_status"], "connected")
        self.assertEqual(speed["value_display"], "21.25")
        self.assertEqual(speed["units_display"], "m/s")
        self.assertEqual(temp["name_display"], "Temp 1")
        self.assertEqual(temp["units_display"], "C")
        self.assertEqual(len(speed_history), 2)
        self.assertEqual([point["value_display"] for point in speed_history], ["18", "21.25"])
        self.assertIn("UTC", speed["received_at_display"])
        self.assertNotIn("+00:00", speed["received_at_display"])


if __name__ == "__main__":
    unittest.main()
