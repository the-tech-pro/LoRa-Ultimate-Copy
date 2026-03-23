from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from echook_lora.protocol import DecodedPacket
from echook_lora.recordings import RecordingManager
from echook_lora.state import TelemetryStore


FLASK_AVAILABLE = importlib.util.find_spec("flask") is not None


@unittest.skipUnless(FLASK_AVAILABLE, "Flask is not installed in this environment.")
class DashboardApiTests(unittest.TestCase):
    def test_dashboard_routes_expose_live_and_recording_endpoints(self) -> None:
        from echook_lora.dashboard import create_app

        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore()
            manager = RecordingManager(Path(tmp))
            packet = DecodedPacket(
                packet_id="s",
                name="speed",
                value=12.3,
                units="m/s",
                received_at=datetime.now(timezone.utc),
                raw=bytes([123, ord("s"), 1, 2, 125]),
            )
            store.update(packet)

            app = create_app(store, manager)
            client = app.test_client()

            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/api/state").status_code, 200)

            start_response = client.post("/api/recordings/start", json={"name": "API Test"})
            self.assertEqual(start_response.status_code, 200)
            manager.record_packet(packet)
            stop_response = client.post("/api/recordings/stop")
            self.assertEqual(stop_response.status_code, 200)

            recordings_payload = client.get("/api/recordings").get_json()
            recording_id = recordings_payload["recordings"][0]["recording_id"]

            self.assertEqual(client.get(f"/recordings/{recording_id}").status_code, 200)
            self.assertEqual(client.get(f"/api/recordings/{recording_id}/state").status_code, 200)


if __name__ == "__main__":
    unittest.main()
