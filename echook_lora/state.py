"""Thread-safe receiver state for the latest telemetry values."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from threading import Lock
from typing import Any

from .constants import (
    DEFAULT_CONNECTION_TIMEOUT_SECONDS,
    DEFAULT_RECENT_HISTORY_POINTS,
    PRIMARY_DASHBOARD_IDS,
    TELEMETRY_DEFINITIONS,
)
from .protocol import DecodedPacket


@dataclass(frozen=True)
class TelemetryReading:
    packet_id: str
    name: str
    value: float
    units: str
    received_at: datetime


@dataclass(frozen=True)
class TelemetryHistoryPoint:
    value: float
    received_at: datetime


class TelemetryStore:
    """Keeps the latest decoded packet per telemetry identifier."""

    def __init__(
        self,
        connection_timeout_seconds: float = DEFAULT_CONNECTION_TIMEOUT_SECONDS,
        recent_history_limit: int = DEFAULT_RECENT_HISTORY_POINTS,
    ) -> None:
        self._connection_timeout_seconds = connection_timeout_seconds
        self._recent_history_limit = recent_history_limit
        self._readings: dict[str, TelemetryReading] = {}
        self._recent_history = {
            packet_id: deque(maxlen=recent_history_limit)
            for packet_id in TELEMETRY_DEFINITIONS
        }
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
            history = self._recent_history.get(packet.packet_id)
            if history is not None:
                history.append(
                    TelemetryHistoryPoint(
                        value=packet.value,
                        received_at=packet.received_at,
                    )
                )
            self._last_packet_at = packet.received_at
            self._last_raw_packet = packet.raw

    def snapshot(self, *, now: datetime | None = None) -> dict[str, Any]:
        with self._lock:
            readings = dict(self._readings)
            recent_history = {
                packet_id: list(history)
                for packet_id, history in self._recent_history.items()
            }
            last_packet_at = self._last_packet_at
            last_raw_packet = self._last_raw_packet

        return build_snapshot(
            readings=readings,
            recent_history=recent_history,
            last_packet_at=last_packet_at,
            last_raw_packet=last_raw_packet,
            now=now,
            connection_timeout_seconds=self._connection_timeout_seconds,
            recent_history_limit=self._recent_history_limit,
        )

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

    @staticmethod
    def _format_value(value: float) -> str:
        return format_value(value)

    @staticmethod
    def _format_units(units: str) -> str:
        return format_units(units)

    @staticmethod
    def _format_name(name: str) -> str:
        return format_name(name)

    @staticmethod
    def _format_timestamp(value: datetime | None, now: datetime) -> str:
        return format_timestamp(value, now)

    @staticmethod
    def _format_age(seconds: float | None) -> str:
        return format_age(seconds)


def build_snapshot(
    *,
    readings: dict[str, TelemetryReading],
    recent_history: dict[str, list[TelemetryHistoryPoint]],
    last_packet_at: datetime | None,
    last_raw_packet: bytes | None,
    now: datetime | None = None,
    connection_timeout_seconds: float = DEFAULT_CONNECTION_TIMEOUT_SECONDS,
    recent_history_limit: int = DEFAULT_RECENT_HISTORY_POINTS,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    packet_age_seconds = None
    if last_packet_at is not None:
        packet_age_seconds = max((current_time - last_packet_at).total_seconds(), 0.0)

    primary = {
        packet_id: serialize_reading(readings.get(packet_id), current_time)
        for packet_id in PRIMARY_DASHBOARD_IDS
    }
    all_readings = {
        packet_id: serialize_reading(reading, current_time)
        for packet_id, reading in sorted(readings.items())
    }
    serialized_history = {
        packet_id: [serialize_history_point(point, current_time) for point in history]
        for packet_id, history in recent_history.items()
    }

    return {
        "connection_status": "connected"
        if packet_age_seconds is not None and packet_age_seconds <= connection_timeout_seconds
        else "waiting",
        "latest_update_time": last_packet_at.isoformat() if last_packet_at else None,
        "latest_update_display": format_timestamp(last_packet_at, current_time),
        "packet_age_seconds": packet_age_seconds,
        "packet_age_display": format_age(packet_age_seconds),
        "primary": primary,
        "all_readings": all_readings,
        "recent_history": serialized_history,
        "recent_history_limit": recent_history_limit,
        "last_raw_packet_hex": last_raw_packet.hex(" ") if last_raw_packet else None,
    }


def serialize_reading(reading: TelemetryReading | None, now: datetime) -> dict[str, Any] | None:
    if reading is None:
        return None

    payload = asdict(reading)
    payload["received_at"] = reading.received_at.isoformat()
    payload["received_at_display"] = format_timestamp(reading.received_at, now)
    payload["age_seconds"] = max((now - reading.received_at).total_seconds(), 0.0)
    payload["age_display"] = format_age(payload["age_seconds"])
    payload["name_display"] = format_name(reading.name)
    payload["units_display"] = format_units(reading.units)
    payload["value_display"] = format_value(reading.value)
    return payload


def serialize_history_point(point: TelemetryHistoryPoint, now: datetime) -> dict[str, Any]:
    return {
        "value": point.value,
        "value_display": format_value(point.value),
        "received_at": point.received_at.isoformat(),
        "received_at_display": format_timestamp(point.received_at, now),
    }


def format_value(value: float) -> str:
    rendered = f"{value:.2f}".rstrip("0").rstrip(".")
    return rendered or "0"


def format_units(units: str) -> str:
    return units


def format_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"([A-Za-z])(\d)", r"\1 \2", name.replace("_", " ")).title()


def format_timestamp(value: datetime | None, now: datetime) -> str:
    if value is None:
        return "Waiting for packets"

    timestamp = value.astimezone(timezone.utc)
    if timestamp.date() == now.astimezone(timezone.utc).date():
        return timestamp.strftime("%H:%M:%S UTC")
    return timestamp.strftime("%d %b %Y %H:%M UTC")


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "Waiting for packets"

    if seconds < 1:
        return "<1s"
    if seconds < 60:
        return f"{seconds:.1f}s"

    whole_seconds = int(round(seconds))
    minutes, remaining_seconds = divmod(whole_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"

    hours, remaining_minutes = divmod(minutes, 60)
    return f"{hours}h {remaining_minutes}m"
