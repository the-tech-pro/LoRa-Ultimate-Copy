#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/install_service.sh receiver --serial-port /dev/serial0 [--baudrate 9600] [--host 0.0.0.0] [--port 5000]
  ./scripts/install_service.sh sender --source-port /dev/ttyUSB0 --lora-port /dev/serial0 [--source-baudrate 115200] [--lora-baudrate 9600]

This script creates a systemd service file for the current repo checkout.
After it finishes, enable boot startup with:
  sudo systemctl enable --now lora-receiver
or
  sudo systemctl enable --now lora-sender
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_value() {
  local flag="$1"
  local value="${2:-}"
  [[ -n "$value" ]] || die "$flag requires a value"
}

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_user="${SUDO_USER:-$USER}"

[[ -x "$repo_dir/.venv/bin/python" ]] || die "Expected virtualenv at $repo_dir/.venv. Run the README setup first."

[[ $# -ge 1 ]] || {
  usage
  exit 1
}

role="$1"
shift

case "$role" in
  receiver)
    serial_port=""
    baudrate="9600"
    host="0.0.0.0"
    port="5000"

    while [[ $# -gt 0 ]]; do
      case "$1" in
        --serial-port)
          require_value "$1" "${2:-}"
          serial_port="$2"
          shift 2
          ;;
        --baudrate)
          require_value "$1" "${2:-}"
          baudrate="$2"
          shift 2
          ;;
        --host)
          require_value "$1" "${2:-}"
          host="$2"
          shift 2
          ;;
        --port)
          require_value "$1" "${2:-}"
          port="$2"
          shift 2
          ;;
        -h|--help)
          usage
          exit 0
          ;;
        *)
          die "Unknown option for receiver: $1"
          ;;
      esac
    done

    [[ -n "$serial_port" ]] || die "--serial-port is required for the receiver service"
    service_name="lora-receiver"
    description="eChook LoRa receiver dashboard"
    exec_command="exec .venv/bin/python receiver_app.py --serial-port $(printf '%q' "$serial_port") --baudrate $(printf '%q' "$baudrate") --host $(printf '%q' "$host") --port $(printf '%q' "$port")"
    ;;
  sender)
    source_port=""
    lora_port=""
    source_baudrate="115200"
    lora_baudrate="9600"

    while [[ $# -gt 0 ]]; do
      case "$1" in
        --source-port)
          require_value "$1" "${2:-}"
          source_port="$2"
          shift 2
          ;;
        --lora-port)
          require_value "$1" "${2:-}"
          lora_port="$2"
          shift 2
          ;;
        --source-baudrate)
          require_value "$1" "${2:-}"
          source_baudrate="$2"
          shift 2
          ;;
        --lora-baudrate)
          require_value "$1" "${2:-}"
          lora_baudrate="$2"
          shift 2
          ;;
        -h|--help)
          usage
          exit 0
          ;;
        *)
          die "Unknown option for sender: $1"
          ;;
      esac
    done

    [[ -n "$source_port" ]] || die "--source-port is required for the sender service"
    [[ -n "$lora_port" ]] || die "--lora-port is required for the sender service"
    service_name="lora-sender"
    description="eChook LoRa sender bridge"
    exec_command="exec .venv/bin/python sender_bridge_app.py --source-port $(printf '%q' "$source_port") --lora-port $(printf '%q' "$lora_port") --source-baudrate $(printf '%q' "$source_baudrate") --lora-baudrate $(printf '%q' "$lora_baudrate")"
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    die "Role must be 'receiver' or 'sender'"
    ;;
esac

service_path="/etc/systemd/system/${service_name}.service"

sudo tee "$service_path" >/dev/null <<EOF
[Unit]
Description=${description}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${service_user}
WorkingDirectory=${repo_dir}
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/env bash -lc '${exec_command}'
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

echo "Installed ${service_name} at ${service_path}"
echo "Next run:"
echo "  sudo systemctl enable --now ${service_name}"
echo "Check status with:"
echo "  sudo systemctl status ${service_name}"
