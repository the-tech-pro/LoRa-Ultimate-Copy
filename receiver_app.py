"""Run the receiver LoRa reader and Flask dashboard together."""

from __future__ import annotations

import argparse
import logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="eChook LoRa receiver dashboard",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--serial-port", default="/dev/ttyS0", help="Receiver LoRa serial device")
    parser.add_argument("--baudrate", type=int, default=9600, help="Receiver LoRa UART baudrate")
    parser.add_argument("--host", default="0.0.0.0", help="Flask bind host")
    parser.add_argument("--port", type=int, default=5000, help="Flask bind port")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        from echook_lora.dashboard import create_app
        from echook_lora.receiver import LoRaReceiver, ReceiverConfig
        from echook_lora.state import TelemetryStore
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

    store = TelemetryStore()
    receiver = LoRaReceiver(
        ReceiverConfig(serial_port=args.serial_port, baudrate=args.baudrate),
        store,
    )
    receiver.start()

    app = create_app(store)
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
