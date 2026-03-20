"""Raw packet validation and eChook value decoding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .constants import END_BYTE, KNOWN_PACKET_IDS, PACKET_SIZE, START_BYTE, TELEMETRY_DEFINITIONS, ZERO_SENTINEL


class PacketError(ValueError):
    """Raised when a packet does not match the expected eChook framing."""


@dataclass(frozen=True)
class RawPacket:
    packet_id: str
    data1: int
    data2: int
    raw: bytes


@dataclass(frozen=True)
class DecodedPacket:
    packet_id: str
    name: str
    value: float
    units: str
    received_at: datetime
    raw: bytes


def normalize_component(value: int) -> int:
    """Treat the eChook zero sentinel as zero."""
    return 0 if value == ZERO_SENTINEL else value


def decode_value(data1: int, data2: int) -> float:
    """Decode an eChook telemetry value using the published rules."""
    if data1 == ZERO_SENTINEL and data2 == ZERO_SENTINEL:
        return 0.0

    if data1 >= 128 and data1 != ZERO_SENTINEL:
        return float(((data1 - 128) * 100) + normalize_component(data2))

    integer_part = normalize_component(data1)
    decimal_part = normalize_component(data2)
    return integer_part + (decimal_part / 100)


def parse_raw_packet(packet: bytes, *, require_known_id: bool = False) -> RawPacket:
    """Parse a single 5-byte eChook packet."""
    if len(packet) != PACKET_SIZE:
        raise PacketError(f"Expected {PACKET_SIZE} bytes, got {len(packet)}")

    if packet[0] != START_BYTE or packet[-1] != END_BYTE:
        raise PacketError("Invalid framing bytes")

    packet_id = chr(packet[1])
    if require_known_id and packet_id not in KNOWN_PACKET_IDS:
        raise PacketError(f"Unknown telemetry identifier: {packet_id!r}")

    return RawPacket(
        packet_id=packet_id,
        data1=packet[2],
        data2=packet[3],
        raw=packet,
    )


def decode_packet(packet: bytes, received_at: datetime | None = None) -> DecodedPacket:
    """Validate a raw packet and decode it into an engineering value."""
    raw_packet = parse_raw_packet(packet, require_known_id=True)
    telemetry = TELEMETRY_DEFINITIONS.get(raw_packet.packet_id)
    timestamp = received_at or datetime.now(timezone.utc)
    name = telemetry.name if telemetry else ""
    units = telemetry.units if telemetry else ""
    return DecodedPacket(
        packet_id=raw_packet.packet_id,
        name=name,
        value=decode_value(raw_packet.data1, raw_packet.data2),
        units=units,
        received_at=timestamp,
        raw=raw_packet.raw,
    )
