#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/install_service.sh receiver [--serial-port /dev/ttyS0] [--baudrate 9600] [--host 0.0.0.0] [--port 5000]
  ./scripts/install_service.sh sender --source-port /dev/ttyUSB0 [--lora-port /dev/ttyS0] [--source-baudrate 115200] [--lora-baudrate 9600]

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

device_unit_name() {
  local device_path="$1"
  systemd-escape -p --suffix=device "$device_path"
}

is_pi_uart_device() {
  local device_path="$1"

  case "$device_path" in
    /dev/ttyS0|/dev/ttyAMA0|/dev/ttyAMA1|/dev/serial0|/dev/serial1)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

ensure_group_membership() {
  local user_name="$1"
  local group_name="$2"

  getent group "$group_name" >/dev/null 2>&1 || return 0

  if id -nG "$user_name" | tr ' ' '\n' | grep -Fxq "$group_name"; then
    return 0
  fi

  sudo usermod -a -G "$group_name" "$user_name"
  added_groups+=("$group_name")
}

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_user="${SUDO_USER:-$USER}"
added_groups=()
supplementary_groups=()
pi_uart_selected="n"
serial_config_changed="n"

[[ -x "$repo_dir/.venv/bin/python" ]] || die "Expected virtualenv at $repo_dir/.venv. Run the README setup first."

[[ $# -ge 1 ]] || {
  usage
  exit 1
}

role="$1"
shift

startup_delay_seconds="5"
after_units=("network-online.target" "systemd-udev-settle.service")
wants_units=("network-online.target" "systemd-udev-settle.service")
device_paths=()

case "$role" in
  receiver)
    serial_port="/dev/ttyS0"
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

    service_name="lora-receiver"
    description="eChook LoRa receiver dashboard"
    exec_command="exec .venv/bin/python receiver_app.py --serial-port $(printf '%q' "$serial_port") --baudrate $(printf '%q' "$baudrate") --host $(printf '%q' "$host") --port $(printf '%q' "$port")"
    device_paths=("$serial_port")
    ;;
  sender)
    source_port=""
    lora_port="/dev/ttyS0"
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
    service_name="lora-sender"
    description="eChook LoRa sender bridge"
    exec_command="exec .venv/bin/python sender_bridge_app.py --source-port $(printf '%q' "$source_port") --lora-port $(printf '%q' "$lora_port") --source-baudrate $(printf '%q' "$source_baudrate") --lora-baudrate $(printf '%q' "$lora_baudrate")"
    device_paths=("$source_port" "$lora_port")
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    die "Role must be 'receiver' or 'sender'"
    ;;
esac

for device_path in "${device_paths[@]}"; do
  after_units+=("$(device_unit_name "$device_path")")
  wants_units+=("$(device_unit_name "$device_path")")
  if is_pi_uart_device "$device_path"; then
    pi_uart_selected="y"
  fi
done

ensure_group_membership "$service_user" "dialout"
if getent group dialout >/dev/null 2>&1; then
  supplementary_groups+=("dialout")
fi

if [[ "$pi_uart_selected" == "y" ]]; then
  if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_serial_cons 1
    sudo raspi-config nonint do_serial_hw 0
    serial_config_changed="y"
  fi

  sudo systemctl disable --now serial-getty@ttyS0.service 2>/dev/null || true
  sudo systemctl disable --now serial-getty@ttyAMA0.service 2>/dev/null || true
  sudo systemctl disable --now serial-getty@ttyAMA1.service 2>/dev/null || true
  sudo systemctl disable --now serial-getty@serial0.service 2>/dev/null || true
  sudo systemctl disable --now serial-getty@serial1.service 2>/dev/null || true
fi

after_line="$(IFS=' '; echo "${after_units[*]}")"
wants_line="$(IFS=' '; echo "${wants_units[*]}")"
supplementary_groups_line="$(IFS=' '; echo "${supplementary_groups[*]}")"
supplementary_groups_directive=""

if [[ -n "$supplementary_groups_line" ]]; then
  supplementary_groups_directive="SupplementaryGroups=${supplementary_groups_line}"
fi

service_path="/etc/systemd/system/${service_name}.service"

sudo tee "$service_path" >/dev/null <<EOF
[Unit]
Description=${description}
After=${after_line}
Wants=${wants_line}

[Service]
Type=simple
User=${service_user}
${supplementary_groups_directive}
WorkingDirectory=${repo_dir}
Environment=PYTHONUNBUFFERED=1
ExecStartPre=/bin/sleep ${startup_delay_seconds}
ExecStart=/usr/bin/env bash -lc '${exec_command}'
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

echo "Installed ${service_name} at ${service_path}"
if ((${#added_groups[@]} > 0)); then
  echo "Added ${service_user} to serial access groups: $(IFS=', '; echo "${added_groups[*]}")"
  echo "If you also run the app manually in a shell, log out and back in before using the serial port directly."
fi
if [[ "$pi_uart_selected" == "y" ]]; then
  echo "Configured Raspberry Pi UART access for on-board serial devices."
  if [[ "$serial_config_changed" == "y" ]]; then
    echo "Reboot recommended so serial console changes take full effect."
  fi
fi
echo "Next run:"
echo "  sudo systemctl enable --now ${service_name}"
echo "Check status with:"
echo "  sudo systemctl status ${service_name}"
