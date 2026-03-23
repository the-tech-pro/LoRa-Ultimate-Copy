"""Flask routes for the live dashboard, recordings, storage, and settings."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file

from .constants import TELEMETRY_DEFINITIONS
from .protocol import PacketError, decode_packet
from .recordings import RecordingError, RecordingManager
from .state import TelemetryStore

TOP_METRIC_IDS = ("v", "s", "i")
GRAPH_DEFAULT_IDS = ("s", "v", "i")
GRAPHABLE_IDS = tuple(packet_id for packet_id in TELEMETRY_DEFINITIONS if packet_id not in {"L", "C", "B"})
SERIES_STYLES = {
    "s": {"label": "Speed", "color": "#14b8a6"},
    "m": {"label": "Motor Speed", "color": "#6366f1"},
    "i": {"label": "Current", "color": "#f59e0b"},
    "v": {"label": "Voltage", "color": "#3b82f6"},
    "w": {"label": "Lower Voltage", "color": "#0ea5e9"},
    "t": {"label": "Throttle Input", "color": "#22c55e"},
    "d": {"label": "Throttle Output", "color": "#f97316"},
    "T": {"label": "Throttle Voltage", "color": "#06b6d4"},
    "a": {"label": "Temp 1", "color": "#ef4444"},
    "b": {"label": "Temp 2", "color": "#ec4899"},
    "c": {"label": "Internal Temp", "color": "#94a3b8"},
    "r": {"label": "Gear Ratio", "color": "#84cc16"},
    "V": {"label": "Ref Voltage", "color": "#a3e635"},
}


def create_app(store: TelemetryStore, recordings: RecordingManager) -> Flask:
    app = Flask(__name__)

    @app.errorhandler(RecordingError)
    def handle_recording_error(error: RecordingError) -> tuple[dict[str, str], int]:
        return {"error": str(error)}, 400

    @app.get("/")
    def index() -> str:
        return render_template(
            "dashboard.html",
            initial_state=_live_payload(store, recordings),
            initial_recordings=recordings.recordings_snapshot(),
            initial_storage=recordings.storage_snapshot(),
            initial_settings=recordings.settings_snapshot(),
            graph_options=_graph_options(),
            top_metric_ids=list(TOP_METRIC_IDS),
            graph_default_ids=list(GRAPH_DEFAULT_IDS),
            metric_styles=_metric_styles(),
        )

    @app.get("/recordings/<recording_id>")
    def recording_playback(recording_id: str) -> str:
        return render_template(
            "playback.html",
            initial_playback=recordings.playback_state(recording_id),
            playback_manifest=recordings.playback_manifest(recording_id),
            graph_options=_graph_options(),
            top_metric_ids=list(TOP_METRIC_IDS),
            graph_default_ids=list(GRAPH_DEFAULT_IDS),
            metric_styles=_metric_styles(),
        )

    @app.get("/api/state")
    def state() -> tuple[dict[str, Any], int]:
        return jsonify(_live_payload(store, recordings)), 200

    @app.get("/api/recordings")
    def recordings_list() -> tuple[dict[str, Any], int]:
        return jsonify(recordings.recordings_snapshot()), 200

    @app.get("/api/recordings/<recording_id>")
    def recording_details(recording_id: str) -> tuple[dict[str, Any], int]:
        return jsonify(recordings.recording_details_snapshot(recording_id)), 200

    @app.get("/api/recordings/<recording_id>/state")
    def recording_state(recording_id: str) -> tuple[dict[str, Any], int]:
        cursor_ms = request.args.get("cursor_ms", type=int)
        return jsonify(recordings.playback_state(recording_id, cursor_ms=cursor_ms)), 200

    @app.post("/api/recordings/start")
    def start_recording() -> tuple[dict[str, Any], int]:
        payload = request.get_json(silent=True) or {}
        return jsonify(recordings.start_recording(payload.get("name"))), 200

    @app.post("/api/recordings/stop")
    def stop_recording() -> tuple[dict[str, Any], int]:
        return jsonify(recordings.stop_recording()), 200

    @app.post("/api/recordings/active/lap")
    def add_lap() -> tuple[dict[str, Any], int]:
        payload = request.get_json(silent=True) or {}
        return jsonify(recordings.add_lap(payload.get("label"))), 200

    @app.post("/api/recordings/<recording_id>/rename")
    def rename_recording(recording_id: str) -> tuple[dict[str, Any], int]:
        payload = request.get_json(silent=True) or {}
        return jsonify(recordings.rename_recording(recording_id, str(payload.get("name", "")))), 200

    @app.delete("/api/recordings/<recording_id>")
    def delete_recording(recording_id: str) -> tuple[dict[str, Any], int]:
        recordings.delete_recording(recording_id)
        return jsonify(recordings.recordings_snapshot()), 200

    @app.get("/api/recordings/<recording_id>/download/raw")
    def download_raw(recording_id: str) -> Response:
        path = recordings.raw_file_path(recording_id)
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.get("/api/recordings/<recording_id>/download/csv")
    def download_csv(recording_id: str) -> Response:
        filename = f"{recording_id}.csv"
        return Response(
            _iter_csv_rows(recordings, recording_id),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/storage")
    def storage() -> tuple[dict[str, Any], int]:
        return jsonify(recordings.storage_snapshot()), 200

    @app.post("/api/storage/purge")
    def purge_storage() -> tuple[dict[str, Any], int]:
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("mode", "quota"))
        deleted = recordings.clear_recordings() if mode == "all" else recordings.purge_oldest()
        return jsonify({"deleted": deleted, "storage": recordings.storage_snapshot()}), 200

    @app.get("/api/settings")
    def settings() -> tuple[dict[str, Any], int]:
        return jsonify(recordings.settings_snapshot()), 200

    @app.post("/api/settings")
    def update_settings() -> tuple[dict[str, Any], int]:
        payload = request.get_json(silent=True) or {}
        return jsonify(recordings.update_settings(payload)), 200

    return app


def _live_payload(store: TelemetryStore, recordings: RecordingManager) -> dict[str, Any]:
    snapshot = store.snapshot()
    snapshot["recording_status"] = recordings.active_status_snapshot()
    snapshot["storage_status"] = recordings.storage_snapshot()
    return snapshot


def _iter_csv_rows(recordings: RecordingManager, recording_id: str):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["received_at", "packet_id", "name", "value", "units", "raw_packet_hex"])
    yield output.getvalue()

    for recorded_packet in recordings.iter_recorded_packets(recording_id):
        try:
            decoded = decode_packet(recorded_packet.raw, received_at=recorded_packet.received_at)
        except PacketError:
            continue

        output.seek(0)
        output.truncate(0)
        writer.writerow(
            [
                recorded_packet.received_at.isoformat(),
                decoded.packet_id,
                decoded.name,
                decoded.value,
                decoded.units,
                recorded_packet.raw.hex(" "),
            ]
        )
        yield output.getvalue()


def _graph_options() -> list[dict[str, str]]:
    return [
        {
            "packet_id": packet_id,
            "label": _series_label(packet_id),
            "color": SERIES_STYLES[packet_id]["color"],
        }
        for packet_id in GRAPHABLE_IDS
    ]


def _metric_styles() -> dict[str, dict[str, str]]:
    return {
        packet_id: {
            "label": _series_label(packet_id),
            "glow": _glow_color(SERIES_STYLES[packet_id]["color"]),
        }
        for packet_id in TOP_METRIC_IDS
    }


def _series_label(packet_id: str) -> str:
    style = SERIES_STYLES.get(packet_id)
    if style:
        return style["label"]

    definition = TELEMETRY_DEFINITIONS[packet_id]
    return re.sub(r"([A-Za-z])(\d)", r"\1 \2", definition.name.replace("_", " ")).title()


def _glow_color(hex_color: str) -> str:
    red = int(hex_color[1:3], 16)
    green = int(hex_color[3:5], 16)
    blue = int(hex_color[5:7], 16)
    return f"rgba({red}, {green}, {blue}, 0.18)"
