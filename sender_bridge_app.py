"""CLI entrypoint for the sender-side eChook to LoRa bridge."""

from __future__ import annotations

import argparse
import logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="eChook UART to LoRa sender bridge")
    parser.add_argument("--source-port", required=True, help="eChook UART device, for example /dev/ttyAMA0")
    parser.add_argument("--lora-port", required=True, help="Sender LoRa serial device, for example /dev/ttyUSB0")
    parser.add_argument("--source-baudrate", type=int, default=9600, help="eChook UART baudrate")
    parser.add_argument("--lora-baudrate", type=int, default=9600, help="LoRa UART baudrate")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        from echook_lora.sender_bridge import SenderBridge, SenderBridgeConfig
    except ImportError as exc:
        parser.exit(
            1,
            f"Missing dependency: {exc.name}. Install the project dependencies with "
            f"'pip install -r requirements.txt'.\n",
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    bridge = SenderBridge(
        SenderBridgeConfig(
            source_port=args.source_port,
            lora_port=args.lora_port,
            source_baudrate=args.source_baudrate,
            lora_baudrate=args.lora_baudrate,
        )
    )
    bridge.run_forever()


if __name__ == "__main__":
    main()
