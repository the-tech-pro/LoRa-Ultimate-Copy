"""Minimal Flask dashboard for live receiver telemetry."""

from __future__ import annotations

from flask import Flask, jsonify, render_template_string

from .constants import PRIMARY_DASHBOARD_IDS
from .state import TelemetryStore

PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="1">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>eChook LoRa Dashboard</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f2f1eb;
        --panel: #fffdf6;
        --ink: #192127;
        --muted: #5c696f;
        --accent: #0f766e;
        --alert: #b42318;
        --border: #d9d3c3;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Georgia, "Times New Roman", serif;
        background:
          radial-gradient(circle at top right, rgba(15, 118, 110, 0.12), transparent 28%),
          linear-gradient(180deg, #f7f5ee 0%, var(--bg) 100%);
        color: var(--ink);
      }
      .page {
        max-width: 1100px;
        margin: 0 auto;
        padding: 24px;
      }
      .hero {
        display: grid;
        gap: 16px;
        margin-bottom: 20px;
      }
      .hero h1 {
        margin: 0;
        font-size: clamp(2rem, 6vw, 4rem);
        line-height: 0.95;
      }
      .hero p {
        margin: 0;
        max-width: 48rem;
        color: var(--muted);
      }
      .status {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        padding: 10px 14px;
        border-radius: 999px;
        background: var(--panel);
        border: 1px solid var(--border);
        width: fit-content;
      }
      .dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: {{ '#0f766e' if snapshot.connection_status == 'connected' else '#b42318' }};
      }
      .cards {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
      }
      .card {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 18px;
        min-height: 140px;
        box-shadow: 0 10px 30px rgba(25, 33, 39, 0.05);
      }
      .label {
        margin: 0 0 10px 0;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
      }
      .value {
        margin: 0;
        font-size: clamp(2rem, 5vw, 3rem);
        line-height: 1;
      }
      .meta {
        margin-top: 8px;
        color: var(--muted);
        font-size: 0.95rem;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        background: var(--panel);
        border-radius: 20px;
        overflow: hidden;
        border: 1px solid var(--border);
      }
      th, td {
        padding: 12px 16px;
        text-align: left;
        border-bottom: 1px solid var(--border);
      }
      th {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
      }
      tr:last-child td {
        border-bottom: 0;
      }
      @media (max-width: 640px) {
        .page { padding: 16px; }
      }
    </style>
  </head>
  <body>
    <main class="page">
      <section class="hero">
        <div class="status">
          <span class="dot"></span>
          <strong>{{ snapshot.connection_status|capitalize }}</strong>
          <span>Packet age:
            {% if snapshot.packet_age_seconds is not none %}
              {{ '%.2f'|format(snapshot.packet_age_seconds) }}s
            {% else %}
              n/a
            {% endif %}
          </span>
        </div>
        <h1>eChook<br>LoRa Telemetry</h1>
        <p>Receiver-side live view of the latest eChook packets. The dashboard refreshes every second and uses receiver timestamps as the source of truth.</p>
      </section>

      <section class="cards">
        {% for card in cards %}
          <article class="card">
            <p class="label">{{ card.label }}</p>
            <p class="value">{{ card.value }}</p>
            <p class="meta">{{ card.meta }}</p>
          </article>
        {% endfor %}
      </section>

      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Value</th>
            <th>Units</th>
            <th>Received</th>
          </tr>
        </thead>
        <tbody>
          {% for reading in all_readings %}
            <tr>
              <td>{{ reading.packet_id }}</td>
              <td>{{ reading.name }}</td>
              <td>{{ reading.value }}</td>
              <td>{{ reading.units or '-' }}</td>
              <td>{{ reading.received_at }}</td>
            </tr>
          {% else %}
            <tr>
              <td colspan="5">Waiting for telemetry packets on the LoRa UART.</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </main>
  </body>
</html>
"""


def create_app(store: TelemetryStore) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        snapshot = store.snapshot()
        cards = [_build_card(packet_id, snapshot["primary"].get(packet_id)) for packet_id in PRIMARY_DASHBOARD_IDS]
        return render_template_string(
            PAGE_TEMPLATE,
            snapshot=snapshot,
            cards=cards,
            all_readings=list(snapshot["all_readings"].values()),
        )

    @app.get("/api/state")
    def state() -> tuple[dict, int]:
        return jsonify(store.snapshot()), 200

    return app


def _build_card(packet_id: str, reading: dict | None) -> dict[str, str]:
    labels = {
        "s": "Speed",
        "v": "Voltage",
        "i": "Current",
        "a": "Temp 1",
        "b": "Temp 2",
        "c": "Internal Temp",
    }
    if reading is None:
        return {"label": labels[packet_id], "value": "--", "meta": "No packet received yet"}

    units = f" {reading['units']}" if reading["units"] else ""
    return {
        "label": labels[packet_id],
        "value": f"{reading['value']}{units}",
        "meta": f"Updated {reading['received_at']}",
    }

