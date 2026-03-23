"""Receiver-side recording, playback, and storage management."""

from __future__ import annotations

from bisect import bisect_right
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
from struct import Struct, error as StructError
from threading import RLock
from typing import Any, BinaryIO, Iterable
from uuid import uuid4

from .constants import (
    DEFAULT_CONNECTION_TIMEOUT_SECONDS,
    DEFAULT_PLAYBACK_SPEED,
    DEFAULT_RECORDING_NAME_PREFIX,
    DEFAULT_RECORDING_QUOTA_BYTES,
    DEFAULT_RECENT_HISTORY_POINTS,
    DEFAULT_RECORDINGS_DIRNAME,
    DEFAULT_RESERVED_FREE_BYTES,
    DEFAULT_SETTINGS_FILENAME,
    TELEMETRY_DEFINITIONS,
)
from .protocol import DecodedPacket, PacketError, decode_packet
from .state import TelemetryHistoryPoint, TelemetryReading, build_snapshot, format_age

MAGIC = b"ECLG"
FORMAT_VERSION = 1
HEADER_STRUCT = Struct(">4sB3xQ")
RECORD_STRUCT = Struct(">Q5s")


class RecordingError(RuntimeError):
    """Raised when a recording operation cannot be completed."""


@dataclass(frozen=True)
class DashboardSettings:
    recording_name_prefix: str = DEFAULT_RECORDING_NAME_PREFIX
    recording_quota_bytes: int = DEFAULT_RECORDING_QUOTA_BYTES
    reserved_free_bytes: int = DEFAULT_RESERVED_FREE_BYTES
    default_playback_speed: float = DEFAULT_PLAYBACK_SPEED


@dataclass(frozen=True)
class RecordingLap:
    label: str
    timestamp: datetime
    offset_ms: int


@dataclass(frozen=True)
class RecordingSummary:
    recording_id: str
    name: str
    started_at: datetime
    ended_at: datetime | None
    packet_count: int
    size_bytes: int
    laps: tuple[RecordingLap, ...]
    raw_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class RecordedPacket:
    received_at: datetime
    raw: bytes


@dataclass(frozen=True)
class _PlaybackReading:
    value: float
    received_at_ms: int


@dataclass(frozen=True)
class _PlaybackFrame:
    cursor_ms: int
    last_packet_ms: int | None
    last_raw_packet: bytes | None
    readings: dict[str, _PlaybackReading]


@dataclass(frozen=True)
class _PlaybackIndex:
    recording_id: str
    first_cursor_ms: int | None
    last_cursor_ms: int | None
    frames: tuple[_PlaybackFrame, ...]
    frame_timestamps: tuple[int, ...]


@dataclass
class _ActiveRecording:
    recording_id: str
    name: str
    started_at: datetime
    raw_path: Path
    metadata_path: Path
    handle: BinaryIO
    packet_count: int = 0
    size_bytes: int = HEADER_STRUCT.size
    laps: list[RecordingLap] | None = None

    def __post_init__(self) -> None:
        if self.laps is None:
            self.laps = []


class SettingsStore:
    """Persist dashboard settings in a small JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = RLock()
        self._settings = self._load()

    def get(self) -> DashboardSettings:
        with self._lock:
            return self._settings

    def snapshot(self) -> dict[str, Any]:
        settings = self.get()
        return {
            "recording_name_prefix": settings.recording_name_prefix,
            "recording_quota_bytes": settings.recording_quota_bytes,
            "recording_quota_display": format_bytes(settings.recording_quota_bytes),
            "reserved_free_bytes": settings.reserved_free_bytes,
            "reserved_free_display": format_bytes(settings.reserved_free_bytes),
            "default_playback_speed": settings.default_playback_speed,
        }

    def update(self, payload: dict[str, Any]) -> DashboardSettings:
        with self._lock:
            current = self._settings
            recording_name_prefix = str(payload.get("recording_name_prefix", current.recording_name_prefix)).strip()
            if not recording_name_prefix:
                recording_name_prefix = DEFAULT_RECORDING_NAME_PREFIX

            recording_quota_bytes = _coerce_positive_int(
                payload.get("recording_quota_bytes", current.recording_quota_bytes),
                "recording_quota_bytes",
            )
            reserved_free_bytes = _coerce_non_negative_int(
                payload.get("reserved_free_bytes", current.reserved_free_bytes),
                "reserved_free_bytes",
            )
            default_playback_speed = _coerce_positive_float(
                payload.get("default_playback_speed", current.default_playback_speed),
                "default_playback_speed",
            )

            self._settings = DashboardSettings(
                recording_name_prefix=recording_name_prefix,
                recording_quota_bytes=recording_quota_bytes,
                reserved_free_bytes=reserved_free_bytes,
                default_playback_speed=default_playback_speed,
            )
            self._path.write_text(json.dumps(asdict(self._settings), indent=2) + "\n", encoding="utf-8")
            return self._settings

    def _load(self) -> DashboardSettings:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            default_settings = DashboardSettings()
            self._path.write_text(json.dumps(asdict(default_settings), indent=2) + "\n", encoding="utf-8")
            return default_settings

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return DashboardSettings()
        try:
            return DashboardSettings(
                recording_name_prefix=str(payload.get("recording_name_prefix", DEFAULT_RECORDING_NAME_PREFIX)).strip()
                or DEFAULT_RECORDING_NAME_PREFIX,
                recording_quota_bytes=_coerce_positive_int(
                    payload.get("recording_quota_bytes", DEFAULT_RECORDING_QUOTA_BYTES),
                    "recording_quota_bytes",
                ),
                reserved_free_bytes=_coerce_non_negative_int(
                    payload.get("reserved_free_bytes", DEFAULT_RESERVED_FREE_BYTES),
                    "reserved_free_bytes",
                ),
                default_playback_speed=_coerce_positive_float(
                    payload.get("default_playback_speed", DEFAULT_PLAYBACK_SPEED),
                    "default_playback_speed",
                ),
            )
        except RecordingError:
            return DashboardSettings()


class RecordingManager:
    """Manage receiver-side recordings and playback data."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._recordings_dir = self._data_dir / DEFAULT_RECORDINGS_DIRNAME
        self._settings = SettingsStore(self._data_dir / DEFAULT_SETTINGS_FILENAME)
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._active: _ActiveRecording | None = None
        self._playback_cache: dict[str, _PlaybackIndex] = {}
        self._seal_incomplete_recordings()

    def record_packet(self, packet: DecodedPacket) -> None:
        with self._lock:
            active = self._active
            if active is None:
                return

            payload = RECORD_STRUCT.pack(to_epoch_ms(packet.received_at), packet.raw)
            active.handle.write(payload)
            active.handle.flush()
            active.packet_count += 1
            active.size_bytes += len(payload)
            self._playback_cache.pop(active.recording_id, None)

    def start_recording(self, name: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self._active is not None:
                raise RecordingError("A recording is already active.")

            blockers = self._start_blockers_locked()
            if blockers:
                raise RecordingError(blockers[0])

            started_at = datetime.now(timezone.utc)
            recording_id = f"{started_at.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
            display_name = (name or "").strip() or self._default_recording_name(started_at)
            raw_path = self._recordings_dir / f"{recording_id}.eclog"
            metadata_path = self._recordings_dir / f"{recording_id}.json"
            handle = raw_path.open("wb")
            handle.write(HEADER_STRUCT.pack(MAGIC, FORMAT_VERSION, to_epoch_ms(started_at)))
            handle.flush()

            active = _ActiveRecording(
                recording_id=recording_id,
                name=display_name,
                started_at=started_at,
                raw_path=raw_path,
                metadata_path=metadata_path,
                handle=handle,
            )
            self._active = active
            self._write_metadata(active, ended_at=None)
            return self.active_status_snapshot()

    def stop_recording(self) -> dict[str, Any]:
        with self._lock:
            active = self._active
            if active is None:
                raise RecordingError("No recording is active.")

            ended_at = datetime.now(timezone.utc)
            active.handle.flush()
            active.handle.close()
            self._write_metadata(active, ended_at=ended_at)
            self._active = None
            self._playback_cache.pop(active.recording_id, None)
            return self.recording_snapshot(self._load_recording_summary(active.recording_id))

    def add_lap(self, label: str | None = None) -> dict[str, Any]:
        with self._lock:
            active = self._active
            if active is None:
                raise RecordingError("No recording is active.")

            timestamp = datetime.now(timezone.utc)
            lap_number = len(active.laps) + 1
            lap = RecordingLap(
                label=(label or "").strip() or f"Lap {lap_number}",
                timestamp=timestamp,
                offset_ms=max(to_epoch_ms(timestamp) - to_epoch_ms(active.started_at), 0),
            )
            active.laps.append(lap)
            self._write_metadata(active, ended_at=None)
            return self.active_status_snapshot()

    def rename_recording(self, recording_id: str, name: str) -> dict[str, Any]:
        trimmed = name.strip()
        if not trimmed:
            raise RecordingError("Recording name cannot be empty.")

        with self._lock:
            if self._active and self._active.recording_id == recording_id:
                self._active.name = trimmed
                self._write_metadata(self._active, ended_at=None)
                return self.active_status_snapshot()

        summary = self._load_recording_summary(recording_id)
        payload = self._read_metadata(summary.metadata_path)
        payload["name"] = trimmed
        self._write_metadata_payload(summary.metadata_path, payload)
        return self.recording_snapshot(self._load_recording_summary(recording_id))

    def delete_recording(self, recording_id: str) -> None:
        with self._lock:
            if self._active and self._active.recording_id == recording_id:
                raise RecordingError("Stop the active recording before deleting it.")

        summary = self._load_recording_summary(recording_id)
        for path in (summary.raw_path, summary.metadata_path):
            if path.exists():
                path.unlink()
        self._playback_cache.pop(recording_id, None)

    def purge_oldest(self) -> list[str]:
        deleted: list[str] = []
        while True:
            snapshot = self.storage_snapshot()
            if snapshot["recordings_bytes"] <= snapshot["recording_quota_bytes"]:
                break

            recordings = [self._load_recording_summary(item["recording_id"]) for item in self.recordings_snapshot()["recordings"]]
            closed_recordings = [summary for summary in recordings if summary.ended_at is not None]
            if not closed_recordings:
                break

            oldest = min(closed_recordings, key=lambda summary: summary.started_at)
            self.delete_recording(oldest.recording_id)
            deleted.append(oldest.recording_id)

        return deleted

    def clear_recordings(self) -> list[str]:
        deleted: list[str] = []
        for summary_payload in self.recordings_snapshot()["recordings"]:
            recording_id = summary_payload["recording_id"]
            with self._lock:
                if self._active and self._active.recording_id == recording_id:
                    continue
            self.delete_recording(recording_id)
            deleted.append(recording_id)
        return deleted

    def active_status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = self._active
            blockers = self._start_blockers_locked()
            if active is None:
                return {
                    "is_recording": False,
                    "can_start_recording": not blockers,
                    "start_blockers": blockers,
                    "active_recording": None,
                }

            now = datetime.now(timezone.utc)
            elapsed_seconds = max((now - active.started_at).total_seconds(), 0.0)
            return {
                "is_recording": True,
                "can_start_recording": False,
                "start_blockers": [],
                "active_recording": {
                    "recording_id": active.recording_id,
                    "name": active.name,
                    "started_at": active.started_at.isoformat(),
                    "started_at_display": active.started_at.strftime("%d %b %Y %H:%M UTC"),
                    "elapsed_seconds": elapsed_seconds,
                    "elapsed_display": format_age(elapsed_seconds),
                    "packet_count": active.packet_count,
                    "size_bytes": active.size_bytes,
                    "size_display": format_bytes(active.size_bytes),
                    "lap_count": len(active.laps),
                    "laps": [lap_snapshot(lap) for lap in active.laps],
                },
            }

    def recordings_snapshot(self) -> dict[str, Any]:
        summaries = [self.recording_snapshot(summary) for summary in self._list_recording_summaries()]
        return {
            "active_recording_id": self._active.recording_id if self._active else None,
            "recordings": summaries,
        }

    def recording_snapshot(self, summary: RecordingSummary) -> dict[str, Any]:
        duration_seconds = None
        if summary.ended_at is not None:
            duration_seconds = max((summary.ended_at - summary.started_at).total_seconds(), 0.0)

        return {
            "recording_id": summary.recording_id,
            "name": summary.name,
            "started_at": summary.started_at.isoformat(),
            "started_at_display": summary.started_at.strftime("%d %b %Y %H:%M UTC"),
            "ended_at": summary.ended_at.isoformat() if summary.ended_at else None,
            "ended_at_display": summary.ended_at.strftime("%d %b %Y %H:%M UTC") if summary.ended_at else "Active",
            "duration_seconds": duration_seconds,
            "duration_display": format_duration(duration_seconds),
            "packet_count": summary.packet_count,
            "size_bytes": summary.size_bytes,
            "size_display": format_bytes(summary.size_bytes),
            "lap_count": len(summary.laps),
            "laps": [lap_snapshot(lap) for lap in summary.laps],
            "is_active": self._active is not None and self._active.recording_id == summary.recording_id,
            "download_raw_url": f"/api/recordings/{summary.recording_id}/download/raw",
            "download_csv_url": f"/api/recordings/{summary.recording_id}/download/csv",
            "playback_url": f"/recordings/{summary.recording_id}",
        }

    def storage_snapshot(self) -> dict[str, Any]:
        total, used, free = shutil.disk_usage(self._data_dir)
        recordings_bytes = 0
        for path in self._recordings_dir.iterdir():
            if path.is_file():
                recordings_bytes += path.stat().st_size

        settings = self._settings.get()
        blockers = self._start_blockers(free, recordings_bytes, settings)
        return {
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "total_display": format_bytes(total),
            "used_display": format_bytes(used),
            "free_display": format_bytes(free),
            "recordings_bytes": recordings_bytes,
            "recordings_display": format_bytes(recordings_bytes),
            "recording_quota_bytes": settings.recording_quota_bytes,
            "recording_quota_display": format_bytes(settings.recording_quota_bytes),
            "reserved_free_bytes": settings.reserved_free_bytes,
            "reserved_free_display": format_bytes(settings.reserved_free_bytes),
            "can_start_recording": not blockers,
            "start_blockers": blockers,
            "recording_count": len(self._list_recording_summaries()),
        }

    def settings_snapshot(self) -> dict[str, Any]:
        return self._settings.snapshot()

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._settings.update(payload)
        return self.settings_snapshot()

    def recording_details_snapshot(self, recording_id: str) -> dict[str, Any]:
        summary = self._load_recording_summary(recording_id)
        manifest = self.playback_manifest(recording_id)
        return {
            **self.recording_snapshot(summary),
            **manifest,
        }

    def playback_manifest(self, recording_id: str) -> dict[str, Any]:
        summary = self._load_recording_summary(recording_id)
        index = self._get_playback_index(recording_id)
        duration_ms = None
        if index.first_cursor_ms is not None and index.last_cursor_ms is not None:
            duration_ms = max(index.last_cursor_ms - index.first_cursor_ms, 0)

        settings = self._settings.get()
        return {
            "recording_id": recording_id,
            "name": summary.name,
            "started_at": summary.started_at.isoformat(),
            "ended_at": summary.ended_at.isoformat() if summary.ended_at else None,
            "duration_ms": duration_ms,
            "frame_count": len(index.frames),
            "first_cursor_ms": index.first_cursor_ms,
            "last_cursor_ms": index.last_cursor_ms,
            "laps": [lap_snapshot(lap) for lap in summary.laps],
            "default_playback_speed": settings.default_playback_speed,
        }

    def playback_state(self, recording_id: str, cursor_ms: int | None = None) -> dict[str, Any]:
        index = self._get_playback_index(recording_id)
        summary = self._load_recording_summary(recording_id)
        if not index.frames:
            empty_snapshot = build_snapshot(
                readings={},
                recent_history={packet_id: [] for packet_id in TELEMETRY_DEFINITIONS},
                last_packet_at=None,
                last_raw_packet=None,
                recent_history_limit=DEFAULT_RECENT_HISTORY_POINTS,
            )
            return {
                **empty_snapshot,
                "cursor_ms": None,
                "duration_ms": 0,
                "recording": self.recording_snapshot(summary),
                "laps": [lap_snapshot(lap) for lap in summary.laps],
            }

        frame_index = len(index.frames) - 1
        if cursor_ms is not None:
            frame_index = max(bisect_right(index.frame_timestamps, cursor_ms) - 1, 0)

        frame = index.frames[frame_index]
        cursor_time = from_epoch_ms(frame.cursor_ms)
        readings = {
            packet_id: TelemetryReading(
                packet_id=packet_id,
                name=TELEMETRY_DEFINITIONS[packet_id].name,
                value=reading.value,
                units=TELEMETRY_DEFINITIONS[packet_id].units,
                received_at=from_epoch_ms(reading.received_at_ms),
            )
            for packet_id, reading in frame.readings.items()
        }

        history_start = max(frame_index - DEFAULT_RECENT_HISTORY_POINTS + 1, 0)
        history_frames = index.frames[history_start : frame_index + 1]
        recent_history = {
            packet_id: [
                TelemetryHistoryPoint(
                    value=playback_frame.readings[packet_id].value,
                    received_at=from_epoch_ms(playback_frame.cursor_ms),
                )
                for playback_frame in history_frames
                if packet_id in playback_frame.readings
            ]
            for packet_id in TELEMETRY_DEFINITIONS
        }
        snapshot = build_snapshot(
            readings=readings,
            recent_history=recent_history,
            last_packet_at=from_epoch_ms(frame.last_packet_ms) if frame.last_packet_ms is not None else None,
            last_raw_packet=frame.last_raw_packet,
            now=cursor_time,
            connection_timeout_seconds=DEFAULT_CONNECTION_TIMEOUT_SECONDS,
            recent_history_limit=DEFAULT_RECENT_HISTORY_POINTS,
        )
        duration_ms = 0
        if index.first_cursor_ms is not None and index.last_cursor_ms is not None:
            duration_ms = max(index.last_cursor_ms - index.first_cursor_ms, 0)
        return {
            **snapshot,
            "cursor_ms": frame.cursor_ms,
            "cursor_time": cursor_time.isoformat(),
            "cursor_display": cursor_time.strftime("%d %b %Y %H:%M:%S UTC"),
            "duration_ms": duration_ms,
            "playback_percent": 0 if not duration_ms else ((frame.cursor_ms - index.first_cursor_ms) / duration_ms) * 100,
            "recording": self.recording_snapshot(summary),
            "laps": [lap_snapshot(lap) for lap in summary.laps],
        }

    def iter_recorded_packets(self, recording_id: str) -> Iterable[RecordedPacket]:
        summary = self._load_recording_summary(recording_id)
        with summary.raw_path.open("rb") as handle:
            header = handle.read(HEADER_STRUCT.size)
            if len(header) != HEADER_STRUCT.size:
                return
            self._validate_header(header)
            while True:
                chunk = handle.read(RECORD_STRUCT.size)
                if len(chunk) < RECORD_STRUCT.size:
                    return
                try:
                    timestamp_ms, raw_packet = RECORD_STRUCT.unpack(chunk)
                except StructError:
                    return
                yield RecordedPacket(received_at=from_epoch_ms(timestamp_ms), raw=raw_packet)

    def raw_file_path(self, recording_id: str) -> Path:
        return self._load_recording_summary(recording_id).raw_path

    def _list_recording_summaries(self) -> list[RecordingSummary]:
        summaries: list[RecordingSummary] = []
        for metadata_path in sorted(self._recordings_dir.glob("*.json")):
            try:
                payload = self._read_metadata(metadata_path)
            except (json.JSONDecodeError, OSError):
                continue

            raw_path = self._recordings_dir / f"{payload['recording_id']}.eclog"
            if not raw_path.exists():
                continue

            laps = tuple(parse_lap(item) for item in payload.get("laps", []))
            ended_at = parse_datetime(payload.get("ended_at"))
            summaries.append(
                RecordingSummary(
                    recording_id=payload["recording_id"],
                    name=payload["name"],
                    started_at=parse_datetime(payload["started_at"]) or datetime.now(timezone.utc),
                    ended_at=ended_at,
                    packet_count=int(payload.get("packet_count", 0)),
                    size_bytes=int(payload.get("size_bytes", raw_path.stat().st_size)),
                    laps=laps,
                    raw_path=raw_path,
                    metadata_path=metadata_path,
                )
            )

        summaries.sort(key=lambda summary: summary.started_at, reverse=True)
        return summaries

    def _load_recording_summary(self, recording_id: str) -> RecordingSummary:
        for summary in self._list_recording_summaries():
            if summary.recording_id == recording_id:
                return summary
        raise RecordingError(f"Recording {recording_id!r} was not found.")

    def _default_recording_name(self, started_at: datetime) -> str:
        prefix = self._settings.get().recording_name_prefix
        return f"{prefix} {started_at.strftime('%d %b %Y %H:%M UTC')}"

    def _write_metadata(self, active: _ActiveRecording, *, ended_at: datetime | None) -> None:
        payload = {
            "recording_id": active.recording_id,
            "name": active.name,
            "started_at": active.started_at.isoformat(),
            "ended_at": ended_at.isoformat() if ended_at else None,
            "packet_count": active.packet_count,
            "size_bytes": active.size_bytes,
            "laps": [lap_snapshot(lap) for lap in active.laps],
        }
        self._write_metadata_payload(active.metadata_path, payload)

    def _write_metadata_payload(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _read_metadata(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _seal_incomplete_recordings(self) -> None:
        for summary in self._list_recording_summaries():
            if summary.ended_at is not None:
                continue

            payload = self._read_metadata(summary.metadata_path)
            packet_count = self._count_packets(summary.raw_path)
            size_bytes = summary.raw_path.stat().st_size
            ended_at = datetime.fromtimestamp(summary.raw_path.stat().st_mtime, tz=timezone.utc)
            payload["ended_at"] = ended_at.isoformat()
            payload["packet_count"] = packet_count
            payload["size_bytes"] = size_bytes
            self._write_metadata_payload(summary.metadata_path, payload)

    def _count_packets(self, path: Path) -> int:
        if not path.exists():
            return 0
        file_size = path.stat().st_size
        if file_size <= HEADER_STRUCT.size:
            return 0
        return max((file_size - HEADER_STRUCT.size) // RECORD_STRUCT.size, 0)

    def _get_playback_index(self, recording_id: str) -> _PlaybackIndex:
        cached = self._playback_cache.get(recording_id)
        if cached is not None:
            return cached

        frames: list[_PlaybackFrame] = []
        current_state: dict[str, _PlaybackReading] = {}
        current_cursor_ms: int | None = None
        first_cursor_ms: int | None = None
        last_packet_ms: int | None = None
        last_raw_packet: bytes | None = None

        for recorded_packet in self.iter_recorded_packets(recording_id):
            timestamp_ms = to_epoch_ms(recorded_packet.received_at)
            bucket_ms = (timestamp_ms // 1000) * 1000
            if current_cursor_ms is None:
                current_cursor_ms = bucket_ms
                first_cursor_ms = bucket_ms

            while current_cursor_ms is not None and current_cursor_ms < bucket_ms:
                frames.append(
                    _PlaybackFrame(
                        cursor_ms=current_cursor_ms,
                        last_packet_ms=last_packet_ms,
                        last_raw_packet=last_raw_packet,
                        readings=dict(current_state),
                    )
                )
                current_cursor_ms += 1000

            try:
                decoded = decode_packet(recorded_packet.raw, received_at=recorded_packet.received_at)
            except PacketError:
                continue

            current_state[decoded.packet_id] = _PlaybackReading(
                value=decoded.value,
                received_at_ms=timestamp_ms,
            )
            last_packet_ms = timestamp_ms
            last_raw_packet = recorded_packet.raw

        if current_cursor_ms is not None:
            frames.append(
                _PlaybackFrame(
                    cursor_ms=current_cursor_ms,
                    last_packet_ms=last_packet_ms,
                    last_raw_packet=last_raw_packet,
                    readings=dict(current_state),
                )
            )

        index = _PlaybackIndex(
            recording_id=recording_id,
            first_cursor_ms=first_cursor_ms,
            last_cursor_ms=frames[-1].cursor_ms if frames else None,
            frames=tuple(frames),
            frame_timestamps=tuple(frame.cursor_ms for frame in frames),
        )
        self._playback_cache[recording_id] = index
        return index

    def _start_blockers_locked(self) -> list[str]:
        storage = self.storage_snapshot()
        return storage["start_blockers"]

    def _start_blockers(self, free_bytes: int, recordings_bytes: int, settings: DashboardSettings) -> list[str]:
        blockers: list[str] = []
        if free_bytes <= settings.reserved_free_bytes:
            blockers.append("Not enough free space remains on the receiver Pi.")
        if recordings_bytes >= settings.recording_quota_bytes:
            blockers.append("Recording quota has been reached. Delete or purge recordings first.")
        return blockers

    def _validate_header(self, header: bytes) -> None:
        try:
            magic, version, _started_at_ms = HEADER_STRUCT.unpack(header)
        except StructError as exc:
            raise RecordingError("Recording header is invalid.") from exc

        if magic != MAGIC or version != FORMAT_VERSION:
            raise RecordingError("Recording format is not supported.")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def parse_lap(payload: dict[str, Any]) -> RecordingLap:
    return RecordingLap(
        label=str(payload.get("label", "Lap")).strip() or "Lap",
        timestamp=parse_datetime(payload.get("timestamp")) or datetime.now(timezone.utc),
        offset_ms=int(payload.get("offset_ms", 0)),
    )


def lap_snapshot(lap: RecordingLap) -> dict[str, Any]:
    return {
        "label": lap.label,
        "timestamp": lap.timestamp.isoformat(),
        "timestamp_display": lap.timestamp.strftime("%H:%M:%S UTC"),
        "offset_ms": lap.offset_ms,
        "offset_display": format_duration(lap.offset_ms / 1000),
    }


def to_epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def from_epoch_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "In progress"

    total_seconds = max(int(round(seconds)), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {remaining_seconds}s"
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def _coerce_positive_int(value: Any, field_name: str) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise RecordingError(f"{field_name} must be an integer.") from exc
    if coerced <= 0:
        raise RecordingError(f"{field_name} must be greater than zero.")
    return coerced


def _coerce_non_negative_int(value: Any, field_name: str) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise RecordingError(f"{field_name} must be an integer.") from exc
    if coerced < 0:
        raise RecordingError(f"{field_name} cannot be negative.")
    return coerced


def _coerce_positive_float(value: Any, field_name: str) -> float:
    try:
        coerced = float(value)
    except (TypeError, ValueError) as exc:
        raise RecordingError(f"{field_name} must be a number.") from exc
    if coerced <= 0:
        raise RecordingError(f"{field_name} must be greater than zero.")
    return coerced
