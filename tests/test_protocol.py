from __future__ import annotations

import unittest
from datetime import datetime, timezone

from echook_lora.protocol import PacketError, decode_packet, decode_value, parse_raw_packet


class ProtocolTests(unittest.TestCase):
    def test_decode_value_matches_prd_examples(self) -> None:
        examples = [
            ((0xFF, 0xFF), 0.0),
            ((12, 34), 12.34),
            ((12, 0xFF), 12.0),
            ((0xFF, 56), 0.56),
            ((129, 23), 123.0),
        ]

        for components, expected in examples:
            with self.subTest(components=components):
                self.assertEqual(decode_value(*components), expected)

    def test_decode_packet_rejects_unknown_id(self) -> None:
        packet = bytes([123, ord("x"), 12, 34, 125])

        with self.assertRaises(PacketError):
            decode_packet(packet, received_at=datetime.now(timezone.utc))

    def test_parse_raw_packet_allows_sender_to_forward_unknown_id(self) -> None:
        packet = bytes([123, ord("x"), 12, 34, 125])

        raw_packet = parse_raw_packet(packet)

        self.assertEqual(raw_packet.packet_id, "x")


if __name__ == "__main__":
    unittest.main()
