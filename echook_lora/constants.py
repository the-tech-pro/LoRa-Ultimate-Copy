"""Project constants and telemetry metadata."""

from __future__ import annotations

from dataclasses import dataclass

PACKET_SIZE = 5
START_BYTE = 123
END_BYTE = 125
ZERO_SENTINEL = 0xFF
DEFAULT_CONNECTION_TIMEOUT_SECONDS = 3.0
DEFAULT_SERIAL_RETRY_DELAY_SECONDS = 1.0
DEFAULT_SERIAL_WRITE_TIMEOUT_SECONDS = 0.5
DEFAULT_SENDER_FLUSH_INTERVAL_SECONDS = 0.2
DEFAULT_RECENT_HISTORY_POINTS = 48


@dataclass(frozen=True)
class TelemetryDefinition:
    packet_id: str
    name: str
    units: str
    description: str


TELEMETRY_DEFINITIONS: dict[str, TelemetryDefinition] = {
    "s": TelemetryDefinition("s", "speed", "m/s", "Vehicle speed"),
    "m": TelemetryDefinition("m", "motor_speed", "RPM", "Motor speed"),
    "i": TelemetryDefinition("i", "current", "A", "Current"),
    "v": TelemetryDefinition("v", "voltage", "V", "Total battery voltage"),
    "w": TelemetryDefinition("w", "lower_voltage", "V", "Lower battery voltage"),
    "t": TelemetryDefinition("t", "throttle_input", "%", "Throttle input"),
    "d": TelemetryDefinition("d", "throttle_output", "%", "Throttle output"),
    "T": TelemetryDefinition("T", "throttle_voltage", "V", "Throttle input voltage"),
    "a": TelemetryDefinition("a", "temp1", "C", "Temperature 1"),
    "b": TelemetryDefinition("b", "temp2", "C", "Temperature 2"),
    "c": TelemetryDefinition("c", "internal_temp", "C", "Internal temperature"),
    "L": TelemetryDefinition("L", "launch_mode", "", "Launch mode / start button"),
    "C": TelemetryDefinition("C", "cycle_view", "", "Cycle view / screen button"),
    "r": TelemetryDefinition("r", "gear_ratio", "", "Calculated gear ratio"),
    "B": TelemetryDefinition("B", "brake_pressed", "", "Brake pressed"),
    "V": TelemetryDefinition("V", "ref_voltage", "V", "ADC reference voltage"),
}

PRIMARY_DASHBOARD_IDS = ("s", "v", "i", "a", "b", "c")
KNOWN_PACKET_IDS = frozenset(TELEMETRY_DEFINITIONS)
