"""Flask dashboard for live receiver telemetry."""

from __future__ import annotations

import re

from flask import Flask, jsonify, render_template_string

from .constants import TELEMETRY_DEFINITIONS
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

PAGE_TEMPLATE = """
<!doctype html>
<html lang="en" data-theme="light">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>eChook LoRa Dashboard</title>
    <script>
      (function() {
        try {
          const savedTheme = localStorage.getItem("dashboard-theme");
          const preferredTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
          document.documentElement.dataset.theme = savedTheme || preferredTheme;
        } catch (error) {
          document.documentElement.dataset.theme = "light";
        }
      }());
    </script>
    <style>
      :root {
        color-scheme: light;
        --page-bg:
          radial-gradient(circle at top left, rgba(59, 130, 246, 0.14), transparent 28%),
          radial-gradient(circle at top right, rgba(20, 184, 166, 0.14), transparent 22%),
          linear-gradient(180deg, #f7fafc 0%, #e7eef5 100%);
        --surface: rgba(255, 255, 255, 0.82);
        --surface-strong: rgba(255, 255, 255, 0.96);
        --surface-soft: rgba(248, 250, 252, 0.82);
        --ink: #10202d;
        --muted: #5d6c79;
        --border: rgba(16, 32, 45, 0.11);
        --shadow: 0 24px 60px rgba(15, 23, 42, 0.10);
        --chart-grid: rgba(16, 32, 45, 0.12);
        --card-highlight: rgba(255, 255, 255, 0.60);
        --status-ok: #166534;
        --status-wait: #b45309;
        --mono: "Cascadia Mono", "JetBrains Mono", "Consolas", monospace;
      }
      html[data-theme="dark"] {
        color-scheme: dark;
        --page-bg:
          radial-gradient(circle at top left, rgba(37, 99, 235, 0.18), transparent 24%),
          radial-gradient(circle at top right, rgba(20, 184, 166, 0.14), transparent 22%),
          linear-gradient(180deg, #08111c 0%, #0e1725 100%);
        --surface: rgba(12, 20, 31, 0.82);
        --surface-strong: rgba(14, 24, 36, 0.96);
        --surface-soft: rgba(18, 30, 46, 0.82);
        --ink: #e2ebf5;
        --muted: #8da0b2;
        --border: rgba(148, 163, 184, 0.18);
        --shadow: 0 28px 70px rgba(2, 6, 23, 0.42);
        --chart-grid: rgba(148, 163, 184, 0.16);
        --card-highlight: rgba(148, 163, 184, 0.08);
        --status-ok: #4ade80;
        --status-wait: #fbbf24;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: "Avenir Next", "Aptos", "Segoe UI Variable", "Trebuchet MS", sans-serif;
        color: var(--ink);
        background: var(--page-bg);
      }
      button,
      input,
      table {
        font: inherit;
      }
      .page {
        max-width: 1260px;
        margin: 0 auto;
        padding: 24px;
      }
      .hero,
      .status-row,
      .metric-grid,
      .chart-toolbar,
      .chart-frame,
      .chart-footer,
      .table-top {
        display: grid;
        gap: 16px;
      }
      .hero {
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: start;
        margin-bottom: 18px;
      }
      .eyebrow,
      .section-tag,
      .metric-label,
      .status-label,
      .selector-meta,
      th {
        margin: 0;
        font-size: 0.76rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--muted);
      }
      .hero h1,
      .chart-title,
      .table-title {
        margin: 10px 0 12px;
        line-height: 0.92;
        letter-spacing: -0.05em;
      }
      .hero h1 {
        font-size: clamp(2.5rem, 5vw, 4.7rem);
      }
      .chart-title,
      .table-title {
        font-size: clamp(1.8rem, 4vw, 2.8rem);
      }
      .hero-copy,
      .status-card,
      .metric-card,
      .chart-card,
      .table-card {
        background: var(--surface);
        border: 1px solid var(--card-highlight);
        box-shadow: var(--shadow);
        border-radius: 28px;
        backdrop-filter: blur(18px);
      }
      .hero-copy,
      .chart-card,
      .table-card {
        padding: 24px;
      }
      .hero-copy p,
      .chart-note,
      .table-note {
        margin: 0;
        max-width: 46rem;
        line-height: 1.6;
        color: var(--muted);
      }
      .hero-actions {
        display: flex;
        justify-content: end;
      }
      .theme-toggle {
        border: 1px solid var(--border);
        background: var(--surface-strong);
        color: var(--ink);
        padding: 12px 16px;
        border-radius: 999px;
        cursor: pointer;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
      }
      .theme-toggle:hover {
        background: var(--surface-soft);
      }
      .status-row {
        grid-template-columns: repeat(4, minmax(0, 1fr));
        margin-bottom: 18px;
      }
      .status-card,
      .metric-card {
        padding: 18px 20px;
        border: 1px solid var(--border);
        min-width: 0;
      }
      .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 12px;
        width: fit-content;
        padding: 12px 14px;
        border-radius: 999px;
        font-weight: 700;
        background: var(--surface-strong);
        border: 1px solid var(--border);
      }
      .status-pill.connected { color: var(--status-ok); }
      .status-pill.waiting { color: var(--status-wait); }
      .dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: currentColor;
        box-shadow: 0 0 0 0 currentColor;
        animation: pulse 2.1s infinite;
      }
      .status-pill.waiting .dot {
        animation: none;
      }
      .status-value,
      .metric-value {
        display: block;
        margin-top: 8px;
        font-size: 1.05rem;
        line-height: 1.4;
        overflow-wrap: anywhere;
      }
      .metric-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
        margin-bottom: 18px;
      }
      .metric-card {
        position: relative;
        overflow: hidden;
      }
      .metric-card::after {
        content: "";
        position: absolute;
        inset: auto -24% -46% auto;
        width: 170px;
        height: 170px;
        border-radius: 50%;
        background: var(--metric-glow, rgba(59, 130, 246, 0.18));
        filter: blur(12px);
        pointer-events: none;
      }
      .metric-head {
        display: flex;
        justify-content: space-between;
        gap: 12px;
      }
      .metric-number-row {
        display: flex;
        align-items: baseline;
        gap: 10px;
        margin: 18px 0 8px;
      }
      .metric-number {
        margin: 0;
        font-size: clamp(2rem, 5vw, 3.4rem);
        line-height: 0.9;
        letter-spacing: -0.05em;
      }
      .metric-unit {
        color: var(--muted);
        font-weight: 700;
      }
      .metric-updated {
        margin: 0;
        color: var(--muted);
      }
      .chart-card {
        margin-bottom: 18px;
      }
      .chart-toolbar {
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: start;
      }
      .selector-list {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }
      .selector-chip {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        padding: 11px 14px;
        border-radius: 999px;
        border: 1px solid var(--border);
        background: var(--surface-soft);
        color: var(--muted);
        cursor: pointer;
        transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
      }
      .selector-chip:hover {
        transform: translateY(-1px);
      }
      .selector-chip.active {
        color: var(--ink);
        background: var(--surface-strong);
        border-color: rgba(148, 163, 184, 0.34);
      }
      .selector-swatch {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        flex: 0 0 auto;
      }
      .selector-label {
        font-weight: 700;
      }
      .selector-value {
        color: var(--muted);
        font-size: 0.94rem;
      }
      .chart-shell {
        margin-top: 18px;
        padding: 18px;
        border-radius: 24px;
        background: var(--surface-soft);
        border: 1px solid var(--border);
      }
      .chart-frame {
        grid-template-columns: auto minmax(0, 1fr);
        align-items: stretch;
      }
      .chart-scale {
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 8px;
        min-width: 64px;
        color: var(--muted);
        font-size: 0.9rem;
        padding-right: 10px;
      }
      .chart-canvas {
        position: relative;
        min-height: 360px;
      }
      .chart-svg {
        width: 100%;
        height: 360px;
        display: block;
      }
      .chart-grid-line {
        stroke: var(--chart-grid);
        stroke-width: 1;
      }
      .chart-axis-line {
        stroke: var(--chart-grid);
        stroke-width: 1.2;
      }
      .chart-path {
        fill: none;
        stroke-width: 3.2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }
      .chart-endpoint {
        stroke: none;
      }
      .chart-empty {
        position: absolute;
        inset: 0;
        display: grid;
        place-items: center;
        padding: 18px;
        text-align: center;
        color: var(--muted);
        border-radius: 20px;
        border: 1px dashed var(--border);
        background: rgba(255, 255, 255, 0.10);
      }
      .hidden {
        display: none;
      }
      .chart-footer {
        grid-template-columns: repeat(3, minmax(0, 1fr));
        margin-top: 14px;
      }
      .chart-stat {
        padding: 14px 16px;
        border-radius: 18px;
        border: 1px solid var(--border);
        background: var(--surface-strong);
      }
      .chart-stat strong {
        display: block;
        margin-top: 6px;
        font-size: 1rem;
        overflow-wrap: anywhere;
      }
      .table-top {
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: start;
      }
      .table-shell {
        overflow-x: auto;
        margin-top: 18px;
        border-radius: 22px;
        border: 1px solid var(--border);
        background: var(--surface-soft);
      }
      table {
        width: 100%;
        border-collapse: collapse;
      }
      th,
      td {
        padding: 14px 16px;
        text-align: left;
        border-bottom: 1px solid var(--border);
        vertical-align: top;
      }
      tr:last-child td {
        border-bottom: 0;
      }
      .table-strong {
        font-weight: 700;
      }
      .mono {
        font-family: var(--mono);
      }
      @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.22); }
        70% { box-shadow: 0 0 0 12px rgba(74, 222, 128, 0); }
        100% { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0); }
      }
      @media (max-width: 1080px) {
        .status-row,
        .metric-grid,
        .chart-footer {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }
      }
      @media (max-width: 820px) {
        .hero,
        .chart-toolbar,
        .table-top,
        .chart-frame {
          grid-template-columns: 1fr;
        }
        .hero-actions {
          justify-content: start;
        }
        .chart-scale {
          flex-direction: row;
          min-width: 0;
          padding-right: 0;
        }
      }
      @media (max-width: 640px) {
        .page {
          padding: 16px;
        }
        .hero-copy,
        .status-card,
        .metric-card,
        .chart-card,
        .table-card {
          border-radius: 22px;
        }
        .hero-copy,
        .chart-card,
        .table-card {
          padding: 18px;
        }
        .status-row,
        .metric-grid,
        .chart-footer {
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
          <p>Key stats stay on top, one large selectable graph sits in the middle, and the full decoded telemetry table stays below. The chart uses a small rolling in-memory sample window, so it stays inside the PRD without adding persistent history.</p>
        </article>
        <div class="hero-actions">
          <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle dashboard theme">Dark mode</button>
        </div>
      </section>

      <section class="status-row">
        <article class="status-card">
          <p class="status-label">Connection</p>
          <div id="status-pill" class="status-pill waiting">
            <span class="dot"></span>
            <span id="status-text">Waiting</span>
          </div>
        </article>
        <article class="status-card">
          <p class="status-label">Last packet</p>
          <strong id="latest-update" class="status-value">Waiting for packets</strong>
        </article>
        <article class="status-card">
          <p class="status-label">Packet age</p>
          <strong id="packet-age" class="status-value">Waiting for packets</strong>
        </article>
        <article class="status-card">
          <p class="status-label">Last raw packet</p>
          <strong id="last-raw-packet" class="status-value mono">n/a</strong>
        </article>
      </section>

      <section id="metric-grid" class="metric-grid"></section>

      <section class="chart-card">
        <div class="chart-toolbar">
          <div>
            <p class="section-tag">Live chart</p>
            <h2 class="chart-title">Selectable telemetry lines</h2>
            <p class="chart-note">Select the stats you want to compare. The graph auto-scales to the selected series so mixed units still remain readable.</p>
          </div>
          <div class="selector-meta">
            <p class="selector-meta">Recent samples: <strong id="history-limit">{{ snapshot.recent_history_limit }}</strong></p>
          </div>
        </div>

        <div id="graph-controls" class="selector-list"></div>

        <div class="chart-shell">
          <div class="chart-frame">
            <div class="chart-scale">
              <span id="chart-max">--</span>
              <span id="chart-min">--</span>
            </div>
            <div class="chart-canvas">
              <svg id="telemetry-chart" class="chart-svg" viewBox="0 0 1000 360" role="img" aria-label="Telemetry chart">
                <g id="chart-grid"></g>
                <g id="chart-lines"></g>
              </svg>
              <div id="chart-empty" class="chart-empty hidden">Select at least one stat with live samples to draw the chart.</div>
            </div>
          </div>

          <div class="chart-footer">
            <article class="chart-stat">
              <p class="status-label">Window</p>
              <strong id="chart-window">Waiting for data</strong>
            </article>
            <article class="chart-stat">
              <p class="status-label">Value range</p>
              <strong id="chart-range">Waiting for data</strong>
            </article>
            <article class="chart-stat">
              <p class="status-label">Visible lines</p>
              <strong id="chart-visible">0 selected</strong>
            </article>
          </div>
        </div>
      </section>

      <section class="table-card">
        <div class="table-top">
          <div>
            <p class="section-tag">All telemetry</p>
            <h2 class="table-title">Latest decoded readings</h2>
          </div>
          <p class="table-note">The table still shows every latest telemetry value, while the graph focuses on the lines you choose.</p>
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
            <tbody id="telemetry-table-body"></tbody>
          </table>
        </div>
      </section>
    </main>

    <script>
      const initialSnapshot = {{ snapshot|tojson }};
      const graphOptions = {{ graph_options|tojson }};
      const topMetricIds = {{ top_metric_ids|tojson }};
      const graphDefaultIds = {{ graph_default_ids|tojson }};
      const metricStyles = {{ metric_styles|tojson }};
      const graphOptionMap = Object.fromEntries(graphOptions.map((option) => [option.packet_id, option]));
      const storageKeys = {
        theme: "dashboard-theme",
        series: "dashboard-series",
      };

      let currentSnapshot = initialSnapshot;
      let selectedIds = loadSelectedIds();

      function loadSelectedIds() {
        try {
          const saved = JSON.parse(localStorage.getItem(storageKeys.series) || "[]");
          const validIds = saved.filter((packetId) => graphOptionMap[packetId]);
          return validIds.length ? validIds : [...graphDefaultIds];
        } catch (error) {
          return [...graphDefaultIds];
        }
      }

      function saveSelectedIds() {
        localStorage.setItem(storageKeys.series, JSON.stringify(selectedIds));
      }

      function formatNumber(value) {
        const rendered = Number(value).toFixed(2).replace(/\\.00$/, "").replace(/(\\.\\d*[1-9])0+$/, "$1");
        return rendered === "-0" ? "0" : rendered;
      }

      function escapeHtml(value) {
        return String(value)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }

      function readingFor(packetId) {
        return currentSnapshot.all_readings[packetId] || null;
      }

      function updateThemeButton() {
        const button = document.getElementById("theme-toggle");
        button.textContent = document.documentElement.dataset.theme === "dark" ? "Light mode" : "Dark mode";
      }

      function toggleTheme() {
        const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = nextTheme;
        localStorage.setItem(storageKeys.theme, nextTheme);
        updateThemeButton();
      }

      function renderStatus() {
        const pill = document.getElementById("status-pill");
        pill.classList.remove("connected", "waiting");
        pill.classList.add(currentSnapshot.connection_status);
        document.getElementById("status-text").textContent = currentSnapshot.connection_status.charAt(0).toUpperCase() + currentSnapshot.connection_status.slice(1);
        document.getElementById("latest-update").textContent = currentSnapshot.latest_update_display || "Waiting for packets";
        document.getElementById("packet-age").textContent = currentSnapshot.packet_age_display || "Waiting for packets";
        document.getElementById("last-raw-packet").textContent = currentSnapshot.last_raw_packet_hex || "n/a";
        document.getElementById("history-limit").textContent = currentSnapshot.recent_history_limit;
      }

      function renderMetricCards() {
        const container = document.getElementById("metric-grid");
        container.innerHTML = topMetricIds.map((packetId) => {
          const reading = readingFor(packetId);
          const style = metricStyles[packetId] || { label: packetId, color: "#3b82f6" };
          const unit = reading && reading.units_display ? reading.units_display : "";
          const value = reading ? reading.value_display : "--";
          const meta = reading ? "Updated " + reading.received_at_display : "Waiting for packets";
          const name = style.label || packetId;
          return `
            <article class="metric-card" style="--metric-glow: ${style.glow};">
              <div class="metric-head">
                <p class="metric-label">${escapeHtml(name)}</p>
                <p class="metric-label mono">${escapeHtml(packetId)}</p>
              </div>
              <div class="metric-number-row">
                <p class="metric-number">${escapeHtml(value)}</p>
                ${unit ? `<span class="metric-unit">${escapeHtml(unit)}</span>` : ""}
              </div>
              <p class="metric-updated">${escapeHtml(meta)}</p>
            </article>
          `;
        }).join("");
      }

      function renderGraphControls() {
        const container = document.getElementById("graph-controls");
        container.innerHTML = graphOptions.map((option) => {
          const reading = readingFor(option.packet_id);
          const value = reading ? `${reading.value_display}${reading.units_display ? ` ${reading.units_display}` : ""}` : "No data";
          const active = selectedIds.includes(option.packet_id) ? "active" : "";
          return `
            <button type="button" class="selector-chip ${active}" data-packet-id="${escapeHtml(option.packet_id)}" aria-pressed="${active ? "true" : "false"}">
              <span class="selector-swatch" style="background: ${option.color};"></span>
              <span class="selector-label">${escapeHtml(option.label)}</span>
              <span class="selector-value">${escapeHtml(value)}</span>
            </button>
          `;
        }).join("");
      }

      function buildGridMarkup(width, height, padding) {
        const lines = [];
        const usableHeight = height - (padding * 2);
        for (let index = 0; index <= 4; index += 1) {
          const y = padding + ((usableHeight / 4) * index);
          lines.push(`<line class="chart-grid-line" x1="${padding}" y1="${y.toFixed(2)}" x2="${(width - padding).toFixed(2)}" y2="${y.toFixed(2)}"></line>`);
        }
        lines.push(`<line class="chart-axis-line" x1="${padding}" y1="${(height - padding).toFixed(2)}" x2="${(width - padding).toFixed(2)}" y2="${(height - padding).toFixed(2)}"></line>`);
        return lines.join("");
      }

      function renderChart() {
        const width = 1000;
        const height = 360;
        const padding = 24;
        const chartGrid = document.getElementById("chart-grid");
        const chartLines = document.getElementById("chart-lines");
        const chartEmpty = document.getElementById("chart-empty");

        chartGrid.innerHTML = buildGridMarkup(width, height, padding);

        const selectedSeries = selectedIds
          .map((packetId) => ({
            packetId,
            option: graphOptionMap[packetId],
            history: currentSnapshot.recent_history[packetId] || [],
          }))
          .filter((series) => series.option);

        const liveSeries = selectedSeries.filter((series) => series.history.length > 0);
        if (!liveSeries.length) {
          chartLines.innerHTML = "";
          chartEmpty.classList.remove("hidden");
          document.getElementById("chart-max").textContent = "--";
          document.getElementById("chart-min").textContent = "--";
          document.getElementById("chart-window").textContent = "Waiting for data";
          document.getElementById("chart-range").textContent = "Waiting for data";
          document.getElementById("chart-visible").textContent = `${selectedIds.length} selected`;
          return;
        }

        const allPoints = liveSeries.flatMap((series) =>
          series.history.map((point) => ({
            timestamp: Date.parse(point.received_at),
            value: Number(point.value),
          }))
        );

        let minTime = Math.min(...allPoints.map((point) => point.timestamp));
        let maxTime = Math.max(...allPoints.map((point) => point.timestamp));
        let minValue = Math.min(...allPoints.map((point) => point.value));
        let maxValue = Math.max(...allPoints.map((point) => point.value));

        if (minTime === maxTime) {
          minTime -= 1000;
          maxTime += 1000;
        }
        if (minValue === maxValue) {
          const pad = Math.max(Math.abs(minValue) * 0.08, 1);
          minValue -= pad;
          maxValue += pad;
        }

        const usableWidth = width - (padding * 2);
        const usableHeight = height - (padding * 2);
        const xFor = (timestamp) => padding + (((timestamp - minTime) / (maxTime - minTime)) * usableWidth);
        const yFor = (value) => height - padding - (((value - minValue) / (maxValue - minValue)) * usableHeight);

        const lineMarkup = liveSeries.map((series) => {
          const points = series.history.map((point) => ({
            x: xFor(Date.parse(point.received_at)),
            y: yFor(Number(point.value)),
          }));

          const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
          const lastPoint = points[points.length - 1];
          return `
            <path class="chart-path" d="${path}" style="stroke: ${series.option.color};"></path>
            <circle class="chart-endpoint" cx="${lastPoint.x.toFixed(2)}" cy="${lastPoint.y.toFixed(2)}" r="4.8" fill="${series.option.color}"></circle>
          `;
        }).join("");

        chartLines.innerHTML = lineMarkup;
        chartEmpty.classList.add("hidden");

        const windowStart = new Date(minTime);
        const windowEnd = new Date(maxTime);
        document.getElementById("chart-max").textContent = formatNumber(maxValue);
        document.getElementById("chart-min").textContent = formatNumber(minValue);
        document.getElementById("chart-window").textContent = `${windowStart.toISOString().slice(11, 19)} UTC to ${windowEnd.toISOString().slice(11, 19)} UTC`;
        document.getElementById("chart-range").textContent = `${formatNumber(minValue)} to ${formatNumber(maxValue)}`;
        document.getElementById("chart-visible").textContent = `${liveSeries.length} visible · ${selectedIds.length} selected`;
      }

      function renderTable() {
        const tableBody = document.getElementById("telemetry-table-body");
        const readings = Object.values(currentSnapshot.all_readings);
        if (!readings.length) {
          tableBody.innerHTML = '<tr><td colspan="5">Waiting for telemetry packets on the LoRa UART.</td></tr>';
          return;
        }

        tableBody.innerHTML = readings.map((reading) => `
          <tr>
            <td class="table-strong mono">${escapeHtml(reading.packet_id)}</td>
            <td>${escapeHtml(reading.name_display)}</td>
            <td class="table-strong">${escapeHtml(reading.value_display)}</td>
            <td>${escapeHtml(reading.units_display || "-")}</td>
            <td>${escapeHtml(reading.received_at_display)}</td>
          </tr>
        `).join("");
      }

      function render() {
        renderStatus();
        renderMetricCards();
        renderGraphControls();
        renderChart();
        renderTable();
        updateThemeButton();
      }

      async function fetchState() {
        try {
          const response = await fetch("/api/state", { cache: "no-store" });
          if (!response.ok) {
            return;
          }
          currentSnapshot = await response.json();
          render();
        } catch (error) {
          // Keep the current snapshot on screen if a poll fails.
        }
      }

      document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
      document.getElementById("graph-controls").addEventListener("click", (event) => {
        const button = event.target.closest("[data-packet-id]");
        if (!button) {
          return;
        }

        const packetId = button.getAttribute("data-packet-id");
        if (selectedIds.includes(packetId)) {
          selectedIds = selectedIds.filter((value) => value !== packetId);
        } else {
          selectedIds = [...selectedIds, packetId];
        }

        saveSelectedIds();
        render();
      });

      render();
      window.setInterval(fetchState, 1000);
    </script>
  </body>
</html>
"""


def create_app(store: TelemetryStore) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        snapshot = store.snapshot()
        return render_template_string(
            PAGE_TEMPLATE,
            snapshot=snapshot,
            graph_options=_graph_options(),
            top_metric_ids=list(TOP_METRIC_IDS),
            graph_default_ids=list(GRAPH_DEFAULT_IDS),
            metric_styles=_metric_styles(),
        )

    @app.get("/api/state")
    def state() -> tuple[dict, int]:
        return jsonify(store.snapshot()), 200

    return app


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
