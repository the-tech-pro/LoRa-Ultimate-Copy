"""Sender-side bridge from eChook UART to LoRa UART."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import serial

from .constants import DEFAULT_SERIAL_RETRY_DELAY_SECONDS, END_BYTE, PACKET_SIZE, START_BYTE
from .protocol import PacketError, parse_raw_packet

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SenderBridgeConfig:
    source_port: str
    lora_port: str
    source_baudrate: int = 115200
    lora_baudrate: int = 115200
    timeout: float = 0.25
    retry_delay_seconds: float = DEFAULT_SERIAL_RETRY_DELAY_SECONDS


class SenderBridge:
    """Forward validated raw 5-byte packets without changing their meaning."""

    def __init__(self, config: SenderBridgeConfig) -> None:
        self._config = config

    def run_forever(self) -> None:
        while True:
            buffer = bytearray()
            try:
                with serial.Serial(
                    self._config.source_port,
                    baudrate=self._config.source_baudrate,
                    timeout=self._config.timeout,
                ) as source, serial.Serial(
                    self._config.lora_port,
                    baudrate=self._config.lora_baudrate,
                    timeout=self._config.timeout,
                ) as lora:
                    LOGGER.info(
                        "Forwarding validated eChook packets from %s to %s",
                        self._config.source_port,
                        self._config.lora_port,
                    )
                    self._transfer_loop(source, lora, buffer)
            except serial.SerialException as exc:
                LOGGER.warning(
                    "Sender bridge serial link unavailable (%s -> %s): %s. Retrying in %.1fs",
                    self._config.source_port,
                    self._config.lora_port,
                    exc,
                    self._config.retry_delay_seconds,
                )
                time.sleep(self._config.retry_delay_seconds)

    def _transfer_loop(self, source: serial.Serial, lora: serial.Serial, buffer: bytearray) -> None:
        while True:
            chunk = source.read(64)
            if not chunk:
                continue
            buffer.extend(chunk)
            self._forward_packets(buffer, lora)

    def _forward_packets(self, buffer: bytearray, lora: serial.Serial) -> None:
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
                parse_raw_packet(candidate)
            except PacketError:
                LOGGER.warning("Dropped invalid sender packet: %s", candidate.hex(" "))
                del buffer[0]
                continue

            lora.write(candidate)
            lora.flush()
            del buffer[:PACKET_SIZE]
