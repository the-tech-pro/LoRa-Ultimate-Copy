"""LoRa receiver service for Raspberry Pi."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Callable

import serial

from .constants import DEFAULT_SERIAL_RETRY_DELAY_SECONDS, END_BYTE, PACKET_SIZE, START_BYTE
from .protocol import DecodedPacket, PacketError, decode_packet
from .state import TelemetryStore

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReceiverConfig:
    serial_port: str
    baudrate: int = 9600
    timeout: float = 0.25
    retry_delay_seconds: float = DEFAULT_SERIAL_RETRY_DELAY_SECONDS


class LoRaReceiver:
    """Read LoRa UART bytes, recover packets, and update receiver state."""

    def __init__(
        self,
        config: ReceiverConfig,
        store: TelemetryStore,
        packet_handler: Callable[[DecodedPacket], None] | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._packet_handler = packet_handler
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="lora-receiver", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            buffer = bytearray()
            try:
                with serial.Serial(
                    self._config.serial_port,
                    baudrate=self._config.baudrate,
                    timeout=self._config.timeout,
                ) as connection:
                    LOGGER.info(
                        "Listening for LoRa telemetry on %s at %s baud",
                        self._config.serial_port,
                        self._config.baudrate,
                    )
                    self._read_loop(connection, buffer)
            except serial.SerialException as exc:
                if self._stop_event.is_set():
                    return

                LOGGER.warning(
                    "LoRa serial link unavailable on %s: %s. Retrying in %.1fs",
                    self._config.serial_port,
                    exc,
                    self._config.retry_delay_seconds,
                )
                self._stop_event.wait(self._config.retry_delay_seconds)

    def _read_loop(self, connection: serial.Serial, buffer: bytearray) -> None:
        while not self._stop_event.is_set():
            chunk = connection.read(64)
            if chunk:
                buffer.extend(chunk)
                self._consume_buffer(buffer)

    def _consume_buffer(self, buffer: bytearray) -> None:
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
                packet = decode_packet(candidate, received_at=datetime.now(timezone.utc))
            except PacketError:
                LOGGER.warning("Dropped invalid packet: %s", candidate.hex(" "))
                del buffer[0]
                continue

            self._store.update(packet)
            if self._packet_handler is not None:
                try:
                    self._packet_handler(packet)
                except Exception:  # pragma: no cover - defensive logging path
                    LOGGER.exception("Packet handler failed for packet %s", candidate.hex(" "))
            del buffer[:PACKET_SIZE]
