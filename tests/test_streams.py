from __future__ import annotations

import unittest

import serial

from echook_lora.receiver import LoRaReceiver, ReceiverConfig
from echook_lora.sender_bridge import SenderBridge, SenderBridgeConfig
from echook_lora.state import TelemetryStore


class FakeLoRa:
    def __init__(self, *, fail_writes: int = 0) -> None:
        self.writes: list[bytes] = []
        self.fail_writes = fail_writes
        self.reset_output_buffer_calls = 0

    def write(self, data: bytes) -> None:
        if self.fail_writes:
            self.fail_writes -= 1
            raise serial.SerialTimeoutException("timed out")
        self.writes.append(data)

    def reset_output_buffer(self) -> None:
        self.reset_output_buffer_calls += 1


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

    def test_sender_keeps_latest_well_framed_packet_per_id(self) -> None:
        bridge = SenderBridge(SenderBridgeConfig(source_port="source", lora_port="lora"))
        pending_packets: dict[str, bytes] = {}
        buffer = bytearray(
            bytes(
                [
                    99,
                    123,
                    ord("s"),
                    1,
                    2,
                    124,
                    123,
                    ord("v"),
                    12,
                    34,
                    125,
                    123,
                    ord("v"),
                    56,
                    78,
                    125,
                    123,
                    ord("x"),
                    1,
                    2,
                    125,
                ]
            )
        )

        bridge._queue_packets(buffer, pending_packets)

        self.assertEqual(
            pending_packets,
            {
                "v": bytes([123, ord("v"), 56, 78, 125]),
                "x": bytes([123, ord("x"), 1, 2, 125]),
            },
        )
        self.assertEqual(buffer, bytearray())

    def test_sender_drops_timed_out_write_and_continues(self) -> None:
        bridge = SenderBridge(SenderBridgeConfig(source_port="source", lora_port="lora"))
        lora = FakeLoRa(fail_writes=1)
        pending_packets = {
            "v": bytes([123, ord("v"), 12, 34, 125]),
            "i": bytes([123, ord("i"), 0xFF, 0xFF, 125]),
        }

        bridge._flush_pending_packets(lora, pending_packets)

        self.assertEqual(lora.writes, [])
        self.assertEqual(lora.reset_output_buffer_calls, 1)
        self.assertEqual(
            pending_packets,
            {
                "v": bytes([123, ord("v"), 12, 34, 125]),
                "i": bytes([123, ord("i"), 0xFF, 0xFF, 125]),
            },
        )

    def test_sender_flushes_latest_packets(self) -> None:
        bridge = SenderBridge(SenderBridgeConfig(source_port="source", lora_port="lora"))
        lora = FakeLoRa()
        pending_packets = {
            "v": bytes([123, ord("v"), 12, 34, 125]),
            "i": bytes([123, ord("i"), 0xFF, 0xFF, 125]),
        }

        bridge._flush_pending_packets(lora, pending_packets)

        self.assertEqual(
            lora.writes,
            [
                bytes([123, ord("v"), 12, 34, 125]),
                bytes([123, ord("i"), 0xFF, 0xFF, 125]),
            ],
        )
        self.assertEqual(pending_packets, {})


if __name__ == "__main__":
    unittest.main()
