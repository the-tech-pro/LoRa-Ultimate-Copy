from __future__ import annotations

import unittest

from echook_lora.receiver import LoRaReceiver, ReceiverConfig
from echook_lora.sender_bridge import SenderBridge, SenderBridgeConfig
from echook_lora.state import TelemetryStore


class FakeLoRa:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def flush(self) -> None:
        return


class StreamTests(unittest.TestCase):
    def test_receiver_discards_noise_and_recovers_packets(self) -> None:
        store = TelemetryStore()
        receiver = LoRaReceiver(ReceiverConfig(serial_port="COM_TEST"), store)
        buffer = bytearray(
            bytes([0, 1, 2, 123, ord("s"), 12, 34, 125, 123, ord("x"), 1, 2, 125, 123, ord("i"), 0xFF, 0xFF, 125])
        )

        receiver._consume_buffer(buffer)
        snapshot = store.snapshot()

        self.assertEqual(buffer, bytearray())
        self.assertIn("s", snapshot["all_readings"])
        self.assertIn("i", snapshot["all_readings"])
        self.assertNotIn("x", snapshot["all_readings"])

    def test_sender_forwards_only_well_framed_packets(self) -> None:
        bridge = SenderBridge(SenderBridgeConfig(source_port="source", lora_port="lora"))
        lora = FakeLoRa()
        buffer = bytearray(
            bytes([99, 123, ord("s"), 1, 2, 124, 123, ord("v"), 12, 34, 125, 123, ord("x"), 1, 2, 125])
        )

        bridge._forward_packets(buffer, lora)

        self.assertEqual(
            lora.writes,
            [
                bytes([123, ord("v"), 12, 34, 125]),
                bytes([123, ord("x"), 1, 2, 125]),
            ],
        )
        self.assertEqual(buffer, bytearray())


if __name__ == "__main__":
    unittest.main()
