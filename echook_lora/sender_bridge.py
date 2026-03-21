"""Sender-side bridge from eChook UART to LoRa UART."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import serial

from .constants import (
    DEFAULT_SERIAL_RETRY_DELAY_SECONDS,
    DEFAULT_SENDER_FLUSH_INTERVAL_SECONDS,
    DEFAULT_SERIAL_WRITE_TIMEOUT_SECONDS,
    END_BYTE,
    PACKET_SIZE,
    START_BYTE,
)
from .protocol import PacketError, parse_raw_packet

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SenderBridgeConfig:
    source_port: str
    lora_port: str
    source_baudrate: int = 115200
    lora_baudrate: int = 9600
    timeout: float = 0.25
    write_timeout: float = DEFAULT_SERIAL_WRITE_TIMEOUT_SECONDS
    flush_interval_seconds: float = DEFAULT_SENDER_FLUSH_INTERVAL_SECONDS
    retry_delay_seconds: float = DEFAULT_SERIAL_RETRY_DELAY_SECONDS


class SenderBridge:
    """Forward validated raw 5-byte packets without changing their meaning."""

    def __init__(self, config: SenderBridgeConfig) -> None:
        self._config = config

    def run_forever(self) -> None:
        while True:
            buffer = bytearray()
            pending_packets: dict[str, bytes] = {}
            try:
                with serial.Serial(
                    self._config.source_port,
                    baudrate=self._config.source_baudrate,
                    timeout=self._config.timeout,
                ) as source, serial.Serial(
                    self._config.lora_port,
                    baudrate=self._config.lora_baudrate,
                    timeout=self._config.timeout,
                    write_timeout=self._config.write_timeout,
                ) as lora:
                    LOGGER.info(
                        "Forwarding validated eChook packets from %s (%s baud) to %s (%s baud) with %.0f ms sender flush interval",
                        self._config.source_port,
                        self._config.source_baudrate,
                        self._config.lora_port,
                        self._config.lora_baudrate,
                        self._config.flush_interval_seconds * 1000,
                    )
                    self._transfer_loop(source, lora, buffer, pending_packets)
            except serial.SerialException as exc:
                LOGGER.warning(
                    "Sender bridge serial link unavailable (%s -> %s): %s. Retrying in %.1fs",
                    self._config.source_port,
                    self._config.lora_port,
                    exc,
                    self._config.retry_delay_seconds,
                )
                time.sleep(self._config.retry_delay_seconds)

    def _transfer_loop(
        self,
        source: serial.Serial,
        lora: serial.Serial,
        buffer: bytearray,
        pending_packets: dict[str, bytes],
    ) -> None:
        next_flush_at = time.monotonic() + self._config.flush_interval_seconds
        while True:
            chunk = source.read(64)
            if chunk:
                buffer.extend(chunk)
                self._queue_packets(buffer, pending_packets)

            now = time.monotonic()
            if now >= next_flush_at:
                self._flush_pending_packets(lora, pending_packets)
                next_flush_at = now + self._config.flush_interval_seconds

    def _queue_packets(self, buffer: bytearray, pending_packets: dict[str, bytes]) -> None:
        while len(buffer) >= PACKET_SIZE:
            start_index = buffer.find(START_BYTE)
            if start_index < 0:
                buffer.clear()
                return

            if start_index > 0:
                del buffer[:start_index]

            if len(buffer) < PACKET_SIZE:
                return

            candidate = bytes(buffer[:PACKET_SIZE])
            if candidate[-1] != END_BYTE:
                del buffer[0]
                continue

            try:
                packet = parse_raw_packet(candidate)
            except PacketError:
                LOGGER.warning("Dropped invalid sender packet: %s", candidate.hex(" "))
                del buffer[0]
                continue

            # Keep only the latest packet per telemetry identifier so the LoRa link
            # is paced by current state rather than every source update.
            pending_packets.pop(packet.packet_id, None)
            pending_packets[packet.packet_id] = candidate
            del buffer[:PACKET_SIZE]

    def _flush_pending_packets(self, lora: serial.Serial, pending_packets: dict[str, bytes]) -> None:
        for packet_id, candidate in list(pending_packets.items()):
            try:
                lora.write(candidate)
            except serial.SerialTimeoutException:
                LOGGER.warning(
                    "LoRa UART write timed out on %s after %.2fs; pending packet %s for id %s was not sent",
                    self._config.lora_port,
                    self._config.write_timeout,
                    candidate.hex(" "),
                    packet_id,
                )
                self._reset_output_buffer(lora)
                return

            del pending_packets[packet_id]

    @staticmethod
    def _reset_output_buffer(connection: serial.Serial) -> None:
        try:
            connection.reset_output_buffer()
        except (AttributeError, serial.SerialException, OSError):
            return
