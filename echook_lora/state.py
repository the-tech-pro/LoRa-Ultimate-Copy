"""Thread-safe receiver state for the latest telemetry values."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from .constants import DEFAULT_CONNECTION_TIMEOUT_SECONDS, PRIMARY_DASHBOARD_IDS, TELEMETRY_DEFINITIONS
from .protocol import DecodedPacket


@dataclass(frozen=True)
class TelemetryReading:
    packet_id: str
    name: str
    value: float
    units: str
    received_at: datetime


class TelemetryStore:
    """Keeps the latest decoded packet per telemetry identifier."""

    def __init__(self, connection_timeout_seconds: float = DEFAULT_CONNECTION_TIMEOUT_SECONDS) -> None:
        self._connection_timeout_seconds = connection_timeout_seconds
        self._readings: dict[str, TelemetryReading] = {}
        self._last_packet_at: datetime | None = None
        self._last_raw_packet: bytes | None = None
        self._lock = Lock()

    def update(self, packet: DecodedPacket) -> None:
        reading = TelemetryReading(
            packet_id=packet.packet_id,
            name=packet.name,
            value=packet.value,
            units=packet.units,
            received_at=packet.received_at,
        )
        with self._lock:
            self._readings[packet.packet_id] = reading
            self._last_packet_at = packet.received_at
            self._last_raw_packet = packet.raw

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            readings = dict(self._readings)
            last_packet_at = self._last_packet_at
            last_raw_packet = self._last_raw_packet

        now = datetime.now(timezone.utc)
        packet_age_seconds = None
        if last_packet_at is not None:
            packet_age_seconds = max((now - last_packet_at).total_seconds(), 0.0)

        primary = {
            packet_id: self._serialize_reading(readings.get(packet_id))
            for packet_id in PRIMARY_DASHBOARD_IDS
        }
        all_readings = {
            packet_id: self._serialize_reading(reading)
            for packet_id, reading in sorted(readings.items())
        }

        return {
            "connection_status": "connected"
            if packet_age_seconds is not None and packet_age_seconds <= self._connection_timeout_seconds
            else "waiting",
            "latest_update_time": last_packet_at.isoformat() if last_packet_at else None,
            "packet_age_seconds": packet_age_seconds,
            "primary": primary,
            "all_readings": all_readings,
            "last_raw_packet_hex": last_raw_packet.hex(" ") if last_raw_packet else None,
        }

    @staticmethod
    def _serialize_reading(reading: TelemetryReading | None) -> dict[str, Any] | None:
        if reading is None:
            return None

        payload = asdict(reading)
        payload["received_at"] = reading.received_at.isoformat()
        return payload

    def known_telemetry(self) -> list[dict[str, str]]:
        return [
            {
                "packet_id": definition.packet_id,
                "name": definition.name,
                "units": definition.units,
                "description": definition.description,
            }
            for definition in TELEMETRY_DEFINITIONS.values()
        ]

