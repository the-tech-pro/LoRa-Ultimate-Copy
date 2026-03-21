"""Flask dashboard for live receiver telemetry."""

from __future__ import annotations

from typing import Iterable

from flask import Flask, jsonify, render_template_string

from .constants import PRIMARY_DASHBOARD_IDS
from .state import TelemetryStore

CARD_STYLES = {
    "s": {
        "label": "Speed",
        "accent": "#0f766e",
        "accent_soft": "rgba(15, 118, 110, 0.18)",
    },
    "v": {
        "label": "Voltage",
        "accent": "#2563eb",
        "accent_soft": "rgba(37, 99, 235, 0.16)",
    },
    "i": {
        "label": "Current",
        "accent": "#d97706",
        "accent_soft": "rgba(217, 119, 6, 0.18)",
    },
    "a": {
        "label": "Temp 1",
        "accent": "#dc2626",
        "accent_soft": "rgba(220, 38, 38, 0.16)",
    },
    "b": {
        "label": "Temp 2",
        "accent": "#be185d",
        "accent_soft": "rgba(190, 24, 93, 0.16)",
    },
    "c": {
        "label": "Internal Temp",
        "accent": "#475569",
        "accent_soft": "rgba(71, 85, 105, 0.18)",
    },
}
TREND_PANEL_IDS = ("s", "v", "i")
TEMPERATURE_IDS = ("a", "b", "c")

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
        --bg: #edf3f1;
        --surface: rgba(255, 255, 255, 0.78);
        --surface-strong: rgba(255, 255, 255, 0.94);
        --ink: #12202b;
        --muted: #61707c;
        --border: rgba(18, 32, 43, 0.10);
        --shadow: 0 24px 60px rgba(18, 32, 43, 0.10);
        --mono: "Cascadia Mono", "JetBrains Mono", "Consolas", monospace;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: "Avenir Next", "Aptos", "Segoe UI Variable", "Trebuchet MS", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(37, 99, 235, 0.14), transparent 32%),
          radial-gradient(circle at top right, rgba(15, 118, 110, 0.14), transparent 28%),
          linear-gradient(180deg, #f6f7f2 0%, var(--bg) 100%);
      }
      .page {
        max-width: 1260px;
        margin: 0 auto;
        padding: 28px;
      }
      .hero,
      .metric-grid,
      .trend-grid {
        display: grid;
        gap: 18px;
      }
      .hero {
        grid-template-columns: minmax(0, 1.25fr) minmax(280px, 0.9fr);
        margin-bottom: 20px;
      }
      .hero-copy,
      .hero-panel,
      .metric-card,
      .trend-card,
      .table-card {
        background: var(--surface);
        border: 1px solid rgba(255, 255, 255, 0.72);
        box-shadow: var(--shadow);
        border-radius: 28px;
        backdrop-filter: blur(16px);
      }
      .hero-copy,
      .hero-panel,
      .table-card {
        padding: 24px;
      }
      .eyebrow,
      .section-tag,
      .metric-label,
      .metric-id,
      .summary-label,
      .trend-label,
      th {
        margin: 0;
        font-size: 0.78rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--muted);
      }
      .hero-copy h1,
      .table-title {
        margin: 10px 0 12px;
        font-size: clamp(2.2rem, 5vw, 4.6rem);
        line-height: 0.92;
        letter-spacing: -0.05em;
      }
      .hero-copy p,
      .hero-note,
      .table-note {
        margin: 0;
        max-width: 42rem;
        color: var(--muted);
        line-height: 1.55;
      }
      .hero-note {
        margin-top: 16px;
      }
      .hero-panel {
        display: grid;
        gap: 16px;
        align-content: start;
      }
      .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 12px;
        width: fit-content;
        padding: 12px 16px;
        border-radius: 999px;
        background: var(--surface-strong);
        border: 1px solid var(--border);
        font-weight: 700;
      }
      .status-pill.connected { color: #166534; }
      .status-pill.waiting { color: #b45309; }
      .status-pill.waiting .dot { animation: none; }
      .dot {
        width: 11px;
        height: 11px;
        border-radius: 50%;
        background: currentColor;
        box-shadow: 0 0 0 0 currentColor;
        animation: pulse 2.2s infinite;
      }
      .summary-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
      }
      .summary-item {
        padding: 14px 16px;
        border-radius: 20px;
        background: var(--surface-strong);
        border: 1px solid var(--border);
        min-width: 0;
      }
      .summary-value {
        display: block;
        margin-top: 6px;
        font-size: 1rem;
        line-height: 1.4;
        overflow-wrap: anywhere;
      }
      .summary-value.mono {
        font-family: var(--mono);
        font-size: 0.95rem;
      }
      .metric-grid {
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        margin-bottom: 20px;
      }
      .metric-card,
      .trend-card {
        padding: 20px;
        border: 1px solid var(--border);
        position: relative;
        overflow: hidden;
      }
      .metric-card::after,
      .trend-card::after {
        content: "";
        position: absolute;
        inset: auto -30% -55% auto;
        width: 180px;
        height: 180px;
        border-radius: 50%;
        background: var(--accent-soft, rgba(15, 118, 110, 0.18));
        filter: blur(10px);
        pointer-events: none;
      }
      .metric-top,
      .trend-top,
      .table-top {
        display: flex;
        align-items: start;
        justify-content: space-between;
        gap: 12px;
      }
      .metric-number-row,
      .trend-value-row {
        display: flex;
        align-items: baseline;
        gap: 10px;
        margin: 16px 0 8px;
      }
      .metric-number,
      .trend-number {
        margin: 0;
        font-size: clamp(2rem, 5vw, 3.2rem);
        line-height: 0.9;
        letter-spacing: -0.05em;
      }
      .metric-unit,
      .trend-unit {
        color: var(--muted);
        font-size: 1rem;
        font-weight: 700;
      }
      .metric-meta,
      .trend-meta {
        margin: 0;
        color: var(--muted);
      }
      .chart-empty {
        display: grid;
        place-items: center;
        min-height: 88px;
        margin-top: 14px;
        padding: 14px;
        border-radius: 18px;
        border: 1px dashed var(--border);
        color: var(--muted);
        background: rgba(255, 255, 255, 0.44);
        text-align: center;
      }
      .sparkline-shell,
      .trend-chart-shell,
      .temperature-chart-shell {
        margin-top: 16px;
        padding: 10px 12px;
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.58);
        border: 1px solid rgba(255, 255, 255, 0.72);
      }
      .sparkline,
      .trend-chart,
      .temperature-chart {
        display: block;
        width: 100%;
        height: auto;
      }
      .chart-grid,
      .chart-axis {
        stroke: rgba(18, 32, 43, 0.12);
        stroke-width: 1;
      }
      .chart-area {
        fill: var(--accent-soft, rgba(15, 118, 110, 0.18));
        stroke: none;
      }
      .chart-line {
        fill: none;
        stroke: var(--accent, #0f766e);
        stroke-width: 3;
        stroke-linecap: round;
        stroke-linejoin: round;
      }
      .chart-line.secondary {
        stroke-width: 2.4;
      }
      .chart-footer,
      .temperature-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        margin-top: 12px;
        color: var(--muted);
        font-size: 0.92rem;
      }
      .trend-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        margin-bottom: 20px;
      }
      .trend-card h2,
      .temperature-title {
        margin: 0;
        font-size: 1.2rem;
        letter-spacing: -0.03em;
      }
      .trend-updated {
        margin: 4px 0 0;
        color: var(--muted);
        text-align: right;
      }
      .temperature-card {
        display: grid;
        gap: 14px;
      }
      .temperature-list {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 10px;
      }
      .temperature-item {
        padding: 12px 14px;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.56);
        border: 1px solid var(--border);
      }
      .temperature-item strong {
        display: block;
        margin-top: 6px;
        font-size: 1.35rem;
        letter-spacing: -0.03em;
      }
      .swatch {
        display: inline-flex;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 8px;
        vertical-align: middle;
      }
      .table-card {
        overflow: hidden;
      }
      .table-title {
        font-size: clamp(1.8rem, 4vw, 2.6rem);
      }
      .table-shell {
        overflow-x: auto;
        margin-top: 18px;
        border-radius: 22px;
        border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.56);
      }
      table {
        width: 100%;
        border-collapse: collapse;
      }
      th,
      td {
        padding: 14px 16px;
        text-align: left;
        border-bottom: 1px solid rgba(18, 32, 43, 0.08);
      }
      td {
        vertical-align: top;
      }
      tr:last-child td {
        border-bottom: 0;
      }
      .cell-strong {
        font-weight: 700;
      }
      .muted {
        color: var(--muted);
      }
      .mono {
        font-family: var(--mono);
      }
      @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(22, 101, 52, 0.22); }
        70% { box-shadow: 0 0 0 12px rgba(22, 101, 52, 0); }
        100% { box-shadow: 0 0 0 0 rgba(22, 101, 52, 0); }
      }
      @media (max-width: 980px) {
        .hero,
        .trend-grid {
          grid-template-columns: 1fr;
        }
      }
      @media (max-width: 640px) {
        .page {
          padding: 16px;
        }
        .hero-copy,
        .hero-panel,
        .metric-card,
        .trend-card,
        .table-card {
          padding: 18px;
          border-radius: 22px;
        }
        .summary-grid {
          grid-template-columns: 1fr;
        }
        th,
        td {
          padding: 12px;
        }
      }
    </style>
  </head>
  <body>
    <main class="page">
      <section class="hero">
        <article class="hero-copy">
          <p class="eyebrow">Receiver-side live telemetry</p>
          <h1>eChook LoRa Dashboard</h1>
          <p>Clean live view of the latest decoded eChook packets. Receiver timestamps stay authoritative, the page refreshes every second, and charts use a small rolling in-memory sample window instead of long-term storage.</p>
          <p class="hero-note">This keeps the dashboard within the PRD: simple local Flask delivery, no persistent history, and fast reading of speed, voltage, current, and temperatures.</p>
        </article>
        <aside class="hero-panel">
          <div class="status-pill {{ snapshot.connection_status }}">
            <span class="dot"></span>
            <span>{{ snapshot.connection_status|capitalize }}</span>
          </div>
          <div class="summary-grid">
            <article class="summary-item">
              <p class="summary-label">Last packet</p>
              <strong class="summary-value">{{ snapshot.latest_update_display }}</strong>
            </article>
            <article class="summary-item">
              <p class="summary-label">Packet age</p>
              <strong class="summary-value">{{ snapshot.packet_age_display }}</strong>
            </article>
            <article class="summary-item">
              <p class="summary-label">Last raw packet</p>
              <strong class="summary-value mono">{{ snapshot.last_raw_packet_hex or "n/a" }}</strong>
            </article>
          </div>
        </aside>
      </section>

      <section class="metric-grid">
        {% for card in cards %}
          <article class="metric-card" style="--accent: {{ card.accent }}; --accent-soft: {{ card.accent_soft }};">
            <div class="metric-top">
              <p class="metric-label">{{ card.label }}</p>
              <p class="metric-id">{{ card.packet_id }}</p>
            </div>
            <div class="metric-number-row">
              <p class="metric-number">{{ card.value }}</p>
              {% if card.unit %}
                <span class="metric-unit">{{ card.unit }}</span>
              {% endif %}
            </div>
            <p class="metric-meta">{{ card.meta }}</p>

            {% if card.chart.has_data %}
              <div class="sparkline-shell">
                <svg class="sparkline" viewBox="{{ card.chart.viewbox }}" aria-hidden="true">
                  <line class="chart-grid" x1="0" y1="{{ card.chart.midline_y }}" x2="{{ card.chart.width }}" y2="{{ card.chart.midline_y }}"></line>
                  <path class="chart-area" d="{{ card.chart.area_path }}"></path>
                  <path class="chart-line" d="{{ card.chart.line_path }}"></path>
                </svg>
              </div>
              <div class="chart-footer">
                <span>{{ card.chart.caption }}</span>
                <span>{{ card.chart.range_label }}</span>
              </div>
            {% else %}
              <div class="chart-empty">Waiting for recent receiver samples.</div>
            {% endif %}
          </article>
        {% endfor %}
      </section>

      <section class="trend-grid">
        {% for panel in trend_panels %}
          <article class="trend-card" style="--accent: {{ panel.accent }}; --accent-soft: {{ panel.accent_soft }};">
            <div class="trend-top">
              <div>
                <p class="trend-label">{{ panel.title }}</p>
                <div class="trend-value-row">
                  <p class="trend-number">{{ panel.value }}</p>
                  {% if panel.unit %}
                    <span class="trend-unit">{{ panel.unit }}</span>
                  {% endif %}
                </div>
              </div>
              <p class="trend-updated">{{ panel.updated }}</p>
            </div>

            {% if panel.chart.has_data %}
              <div class="trend-chart-shell">
                <svg class="trend-chart" viewBox="{{ panel.chart.viewbox }}" aria-hidden="true">
                  <line class="chart-grid" x1="0" y1="{{ panel.chart.topline_y }}" x2="{{ panel.chart.width }}" y2="{{ panel.chart.topline_y }}"></line>
                  <line class="chart-grid" x1="0" y1="{{ panel.chart.midline_y }}" x2="{{ panel.chart.width }}" y2="{{ panel.chart.midline_y }}"></line>
                  <line class="chart-axis" x1="0" y1="{{ panel.chart.baseline_y }}" x2="{{ panel.chart.width }}" y2="{{ panel.chart.baseline_y }}"></line>
                  <path class="chart-area" d="{{ panel.chart.area_path }}"></path>
                  <path class="chart-line" d="{{ panel.chart.line_path }}"></path>
                </svg>
              </div>
              <div class="chart-footer">
                <span>{{ panel.chart.caption }}</span>
                <span>{{ panel.chart.range_label }}</span>
              </div>
            {% else %}
              <div class="chart-empty">Waiting for live samples for this trend.</div>
            {% endif %}
          </article>
        {% endfor %}

        <article class="trend-card temperature-card">
          <div class="trend-top">
            <div>
              <p class="trend-label">Temperature comparison</p>
              <h2 class="temperature-title">Recent receiver samples</h2>
            </div>
            <p class="trend-updated">{{ temperature_panel.updated }}</p>
          </div>

          <div class="temperature-list">
            {% for item in temperature_panel.series %}
              <article class="temperature-item">
                <p class="summary-label"><span class="swatch" style="background: {{ item.accent }};"></span>{{ item.label }}</p>
                <strong>{{ item.value }}{% if item.unit %} {{ item.unit }}{% endif %}</strong>
                <span class="muted">{{ item.updated }}</span>
              </article>
            {% endfor %}
          </div>

          {% if temperature_panel.chart.has_data %}
            <div class="temperature-chart-shell">
              <svg class="temperature-chart" viewBox="{{ temperature_panel.chart.viewbox }}" aria-hidden="true">
                <line class="chart-grid" x1="0" y1="{{ temperature_panel.chart.topline_y }}" x2="{{ temperature_panel.chart.width }}" y2="{{ temperature_panel.chart.topline_y }}"></line>
                <line class="chart-grid" x1="0" y1="{{ temperature_panel.chart.midline_y }}" x2="{{ temperature_panel.chart.width }}" y2="{{ temperature_panel.chart.midline_y }}"></line>
                <line class="chart-axis" x1="0" y1="{{ temperature_panel.chart.baseline_y }}" x2="{{ temperature_panel.chart.width }}" y2="{{ temperature_panel.chart.baseline_y }}"></line>
                {% for line in temperature_panel.chart.lines %}
                  <path class="chart-line secondary" d="{{ line.path }}" style="stroke: {{ line.color }};"></path>
                {% endfor %}
              </svg>
            </div>
            <div class="temperature-footer">
              <span>{{ temperature_panel.chart.caption }}</span>
              <span>{{ temperature_panel.chart.range_label }}</span>
            </div>
          {% else %}
            <div class="chart-empty">Waiting for recent temperature samples.</div>
          {% endif %}
        </article>
      </section>

      <section class="table-card">
        <div class="table-top">
          <div>
            <p class="section-tag">All telemetry</p>
            <h2 class="table-title">Latest decoded readings</h2>
          </div>
          <p class="table-note">Table timestamps are shortened to keep the layout clean on laptop and phone screens.</p>
        </div>

        <div class="table-shell">
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
                  <td class="cell-strong mono">{{ reading.packet_id }}</td>
                  <td>{{ reading.name_display }}</td>
                  <td class="cell-strong">{{ reading.value_display }}</td>
                  <td>{{ reading.units_display or "-" }}</td>
                  <td>{{ reading.received_at_display }}</td>
                </tr>
              {% else %}
                <tr>
                  <td colspan="5">Waiting for telemetry packets on the LoRa UART.</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </body>
</html>
"""


def create_app(store: TelemetryStore) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        snapshot = store.snapshot()
        cards = [
            _build_card(
                packet_id,
                snapshot["primary"].get(packet_id),
                snapshot["recent_history"].get(packet_id, []),
            )
            for packet_id in PRIMARY_DASHBOARD_IDS
        ]
        trend_panels = [
            _build_trend_panel(
                packet_id,
                snapshot["primary"].get(packet_id),
                snapshot["recent_history"].get(packet_id, []),
            )
            for packet_id in TREND_PANEL_IDS
        ]
        temperature_panel = _build_temperature_panel(snapshot)

        return render_template_string(
            PAGE_TEMPLATE,
            snapshot=snapshot,
            cards=cards,
            trend_panels=trend_panels,
            temperature_panel=temperature_panel,
            all_readings=list(snapshot["all_readings"].values()),
        )

    @app.get("/api/state")
    def state() -> tuple[dict, int]:
        return jsonify(store.snapshot()), 200

    return app


def _build_card(packet_id: str, reading: dict | None, history: list[dict]) -> dict[str, object]:
    style = CARD_STYLES[packet_id]
    unit = reading["units_display"] if reading else ""
    return {
        "packet_id": packet_id,
        "label": style["label"],
        "value": reading["value_display"] if reading else "--",
        "unit": unit,
        "meta": f"Updated {reading['received_at_display']}" if reading else "Waiting for live data",
        "accent": style["accent"],
        "accent_soft": style["accent_soft"],
        "chart": _build_chart(history, accent=style["accent"], accent_soft=style["accent_soft"], width=280, height=92, unit=unit),
    }


def _build_trend_panel(packet_id: str, reading: dict | None, history: list[dict]) -> dict[str, object]:
    style = CARD_STYLES[packet_id]
    unit = reading["units_display"] if reading else ""
    return {
        "title": f"{style['label']} trend",
        "value": reading["value_display"] if reading else "--",
        "unit": unit,
        "updated": reading["received_at_display"] if reading else "Waiting for packets",
        "accent": style["accent"],
        "accent_soft": style["accent_soft"],
        "chart": _build_chart(history, accent=style["accent"], accent_soft=style["accent_soft"], width=520, height=190, unit=unit),
    }


def _build_temperature_panel(snapshot: dict) -> dict[str, object]:
    series = []
    chart_series = []
    updated_points = []

    for packet_id in TEMPERATURE_IDS:
        style = CARD_STYLES[packet_id]
        reading = snapshot["primary"].get(packet_id)
        history = snapshot["recent_history"].get(packet_id, [])
        series.append(
            {
                "label": style["label"],
                "value": reading["value_display"] if reading else "--",
                "unit": reading["units_display"] if reading else "",
                "updated": reading["received_at_display"] if reading else "Waiting for packets",
                "accent": style["accent"],
            }
        )
        chart_series.append(
            {
                "color": style["accent"],
                "history": history,
            }
        )
        if reading:
            updated_points.append((reading["received_at"], reading["received_at_display"]))

    return {
        "series": series,
        "updated": max(updated_points)[1] if updated_points else "Waiting for packets",
        "chart": _build_multi_series_chart(chart_series, width=520, height=190, unit=series[0]["unit"] if series else ""),
    }


def _build_chart(
    history: list[dict],
    *,
    accent: str,
    accent_soft: str,
    width: int,
    height: int,
    unit: str,
) -> dict[str, object]:
    if not history:
        return {"has_data": False}

    padding = 12
    values = [point["value"] for point in history]
    coordinates, baseline_y, topline_y, midline_y = _build_coordinates(values, width=width, height=height, padding=padding)
    line_path = _line_path(coordinates)
    area_path = _area_path(coordinates, baseline_y)

    return {
        "has_data": True,
        "accent": accent,
        "accent_soft": accent_soft,
        "viewbox": f"0 0 {width} {height}",
        "width": width,
        "height": height,
        "topline_y": f"{topline_y:.2f}",
        "midline_y": f"{midline_y:.2f}",
        "baseline_y": f"{baseline_y:.2f}",
        "line_path": line_path,
        "area_path": area_path,
        "caption": _sample_caption(len(history)),
        "range_label": _range_label(min(values), max(values), unit),
    }


def _build_multi_series_chart(
    series: list[dict[str, object]],
    *,
    width: int,
    height: int,
    unit: str,
) -> dict[str, object]:
    populated_series = [item for item in series if item["history"]]
    if not populated_series:
        return {"has_data": False}

    padding = 12
    values = [point["value"] for item in populated_series for point in item["history"]]
    chart_lines = []
    min_value = min(values)
    max_value = max(values)
    baseline_y = height - padding
    topline_y = float(padding)
    midline_y = height / 2

    for item in populated_series:
        history = item["history"]
        coordinates, _, _, _ = _build_coordinates(
            [point["value"] for point in history],
            width=width,
            height=height,
            padding=padding,
            min_value=min_value,
            max_value=max_value,
        )
        chart_lines.append(
            {
                "path": _line_path(coordinates),
                "color": item["color"],
            }
        )

    sample_count = max(len(item["history"]) for item in populated_series)
    return {
        "has_data": True,
        "viewbox": f"0 0 {width} {height}",
        "width": width,
        "height": height,
        "topline_y": f"{topline_y:.2f}",
        "midline_y": f"{midline_y:.2f}",
        "baseline_y": f"{baseline_y:.2f}",
        "lines": chart_lines,
        "caption": _sample_caption(sample_count),
        "range_label": _range_label(min_value, max_value, unit),
    }


def _build_coordinates(
    values: list[float],
    *,
    width: int,
    height: int,
    padding: int,
    min_value: float | None = None,
    max_value: float | None = None,
) -> tuple[list[tuple[float, float]], float, float, float]:
    baseline_y = float(height - padding)
    topline_y = float(padding)
    midline_y = height / 2
    chart_width = width - (padding * 2)
    chart_height = height - (padding * 2)

    lower = min(values) if min_value is None else min_value
    upper = max(values) if max_value is None else max_value
    span = upper - lower
    if span == 0:
        span = 1.0
        lower -= 0.5

    if len(values) == 1:
        x_positions = [float(padding), float(width - padding)]
        values = [values[0], values[0]]
    else:
        step = chart_width / (len(values) - 1)
        x_positions = [padding + (index * step) for index in range(len(values))]

    coordinates = []
    for x, value in zip(x_positions, values):
        ratio = (value - lower) / span
        y = baseline_y - (ratio * chart_height)
        coordinates.append((x, y))

    return coordinates, baseline_y, topline_y, midline_y


def _line_path(coordinates: Iterable[tuple[float, float]]) -> str:
    return " ".join(
        ("M" if index == 0 else "L") + f" {x:.2f} {y:.2f}"
        for index, (x, y) in enumerate(coordinates)
    )


def _area_path(coordinates: list[tuple[float, float]], baseline_y: float) -> str:
    first_x, _ = coordinates[0]
    last_x, _ = coordinates[-1]
    return f"{_line_path(coordinates)} L {last_x:.2f} {baseline_y:.2f} L {first_x:.2f} {baseline_y:.2f} Z"


def _sample_caption(sample_count: int) -> str:
    if sample_count == 1:
        return "1 recent receiver sample"
    return f"{sample_count} recent receiver samples"


def _range_label(min_value: float, max_value: float, unit: str) -> str:
    suffix = f" {unit}" if unit else ""
    return f"Range {_format_value(min_value)} to {_format_value(max_value)}{suffix}"


def _format_value(value: float) -> str:
    rendered = f"{value:.2f}".rstrip("0").rstrip(".")
    return rendered or "0"
