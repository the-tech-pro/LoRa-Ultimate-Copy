#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/setup.sh

Interactive setup wizard for the eChook LoRa project.

What it does:
  - installs required system packages
  - creates or reuses .venv
  - installs Python dependencies
  - configures either the receiver or sender service
  - optionally configures receiver networking

This script is intended to be run from the cloned repo on a Raspberry Pi.
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

prompt_with_default() {
  local prompt="$1"
  local default_value="$2"
  local value

  read -r -p "$prompt [$default_value]: " value
  printf '%s\n' "${value:-$default_value}"
}

prompt_yes_no() {
  local prompt="$1"
  local default_choice="$2"
  local reply
  local normalized_default

  case "$default_choice" in
    y|Y) normalized_default="y" ;;
    n|N) normalized_default="n" ;;
    *) die "prompt_yes_no default must be y or n" ;;
  esac

  while true; do
    if [[ "$normalized_default" == "y" ]]; then
      read -r -p "$prompt [Y/n]: " reply
    else
      read -r -p "$prompt [y/N]: " reply
    fi

    reply="${reply:-$normalized_default}"
    case "$reply" in
      y|Y) return 0 ;;
      n|N) return 1 ;;
      *) echo "Please answer y or n." ;;
    esac
  done
}

prompt_choice() {
  local prompt="$1"
  shift
  local options=("$@")
  local reply

  printf '%s\n' "$prompt" >&2
  local index=1
  for option in "${options[@]}"; do
    printf '  %s. %s\n' "$index" "$option" >&2
    index=$((index + 1))
  done

  while true; do
    read -r -p "Choose an option [1-${#options[@]}]: " reply
    [[ "$reply" =~ ^[0-9]+$ ]] || {
      echo "Enter a number." >&2
      continue
    }
    if (( reply >= 1 && reply <= ${#options[@]} )); then
      printf '%s\n' "$reply"
      return 0
    fi
    echo "Choose a number between 1 and ${#options[@]}." >&2
  done
}

install_python_environment() {
  echo
  echo "Installing system packages"
  sudo apt update
  sudo apt install -y python3 python3-venv python3-pip

  if [[ ! -x "$repo_dir/.venv/bin/python" ]]; then
    echo "Creating virtual environment"
    python3 -m venv "$repo_dir/.venv"
  fi

  echo "Installing Python dependencies"
  "$repo_dir/.venv/bin/pip" install --upgrade pip
  "$repo_dir/.venv/bin/pip" install -r "$repo_dir/requirements.txt"
}

configure_receiver_networking() {
  local networking_choice
  local mode

  networking_choice="$(prompt_choice \
    "Receiver networking mode:" \
    "Keep existing/shared network and do not change networking" \
    "Direct Ethernet to laptop or iPad (recommended for Pi 4 B)" \
    "Receiver hotspot Wi-Fi network")"

  case "$networking_choice" in
    1)
      receiver_networking_mode="none"
      ;;
    2)
      receiver_networking_mode="ethernet"
      ;;
    3)
      receiver_networking_mode="hotspot"
      ;;
  esac

  case "$receiver_networking_mode" in
    none)
      return 0
      ;;
    ethernet)
      receiver_eth_interface="$(prompt_with_default "Ethernet interface" "eth0")"
      receiver_network_address="$(prompt_with_default "Receiver Ethernet IP" "192.168.7.1")"
      receiver_dhcp_start="$(prompt_with_default "Ethernet DHCP start" "192.168.7.20")"
      receiver_dhcp_end="$(prompt_with_default "Ethernet DHCP end" "192.168.7.150")"
      ;;
    hotspot)
      receiver_wlan_interface="$(prompt_with_default "Wi-Fi interface" "wlan0")"
      receiver_network_address="$(prompt_with_default "Receiver hotspot IP" "192.168.50.1")"
      receiver_dhcp_start="$(prompt_with_default "Hotspot DHCP start" "192.168.50.20")"
      receiver_dhcp_end="$(prompt_with_default "Hotspot DHCP end" "192.168.50.150")"
      receiver_hotspot_channel="$(prompt_with_default "Hotspot channel" "6")"
      receiver_hotspot_country="$(prompt_with_default "Hotspot country code" "US")"

      echo "Hotspot defaults:"
      echo "  SSID: egr-echook"
      echo "  Password: Florence!"
      if prompt_yes_no "Override the hotspot SSID and password?" "n"; then
        receiver_hotspot_ssid="$(prompt_with_default "Hotspot SSID" "egr-echook")"
        receiver_hotspot_passphrase="$(prompt_with_default "Hotspot password" "Florence!")"
      else
        receiver_hotspot_ssid="egr-echook"
        receiver_hotspot_passphrase="Florence!"
      fi
      ;;
  esac
}

run_receiver_networking_install() {
  case "$receiver_networking_mode" in
    none)
      echo "Leaving receiver networking unchanged"
      ;;
    ethernet)
      bash "$repo_dir/scripts/install_receiver_networking.sh" ethernet \
        --eth "$receiver_eth_interface" \
        --address "$receiver_network_address" \
        --dhcp-start "$receiver_dhcp_start" \
        --dhcp-end "$receiver_dhcp_end" \
        --port "$receiver_dashboard_port"
      reboot_recommended="y"
      ;;
    hotspot)
      bash "$repo_dir/scripts/install_receiver_networking.sh" hotspot \
        --wlan "$receiver_wlan_interface" \
        --address "$receiver_network_address" \
        --dhcp-start "$receiver_dhcp_start" \
        --dhcp-end "$receiver_dhcp_end" \
        --channel "$receiver_hotspot_channel" \
        --country "$receiver_hotspot_country" \
        --ssid "$receiver_hotspot_ssid" \
        --passphrase "$receiver_hotspot_passphrase" \
        --port "$receiver_dashboard_port"
      reboot_recommended="y"
      ;;
  esac
}

configure_receiver() {
  echo
  echo "Receiver setup"

  receiver_serial_port="$(prompt_with_default "Receiver LoRa serial port" "/dev/ttyS0")"
  receiver_baudrate="$(prompt_with_default "Receiver LoRa baudrate" "9600")"
  receiver_dashboard_host="$(prompt_with_default "Receiver dashboard bind host" "0.0.0.0")"
  receiver_dashboard_port="$(prompt_with_default "Receiver dashboard port" "5000")"
  receiver_install_service="y"
  receiver_networking_mode="none"
  receiver_eth_interface=""
  receiver_wlan_interface=""
  receiver_network_address=""
  receiver_dhcp_start=""
  receiver_dhcp_end=""
  receiver_hotspot_channel="6"
  receiver_hotspot_country="US"
  receiver_hotspot_ssid="egr-echook"
  receiver_hotspot_passphrase="Florence!"

  configure_receiver_networking

  install_python_environment
  run_receiver_networking_install

  if prompt_yes_no "Install and enable lora-receiver as a boot service?" "y"; then
    bash "$repo_dir/scripts/install_service.sh" receiver \
      --serial-port "$receiver_serial_port" \
      --baudrate "$receiver_baudrate" \
      --host "$receiver_dashboard_host" \
      --port "$receiver_dashboard_port"
    sudo systemctl enable --now lora-receiver
    receiver_install_service="y"
  else
    receiver_install_service="n"
  fi

  echo
  echo "Receiver setup complete."
  echo "LoRa serial: ${receiver_serial_port} @ ${receiver_baudrate}"
  if [[ "$receiver_install_service" == "y" ]]; then
    echo "Service: lora-receiver"
  else
    echo "Service: not installed"
    echo "Run manually with: .venv/bin/python receiver_app.py --serial-port ${receiver_serial_port} --baudrate ${receiver_baudrate} --host ${receiver_dashboard_host} --port ${receiver_dashboard_port}"
  fi
  case "$receiver_networking_mode" in
    ethernet)
      echo "Dashboard URL: http://${receiver_network_address}:${receiver_dashboard_port}"
      ;;
    hotspot)
      echo "Dashboard URL: http://${receiver_network_address}:${receiver_dashboard_port}"
      echo "Hotspot SSID: ${receiver_hotspot_ssid}"
      echo "Hotspot password: ${receiver_hotspot_passphrase}"
      ;;
    none)
      echo "Dashboard URL: http://<receiver-pi-ip>:${receiver_dashboard_port}"
      ;;
  esac
}

configure_sender() {
  echo
  echo "Sender setup"

  sender_source_port="$(prompt_with_default "eChook source serial port" "/dev/ttyUSB0")"
  sender_source_baudrate="$(prompt_with_default "eChook source baudrate" "115200")"
  sender_lora_port="$(prompt_with_default "LoRa serial port" "/dev/ttyS0")"
  sender_lora_baudrate="$(prompt_with_default "LoRa baudrate" "9600")"
  sender_install_service="y"

  install_python_environment

  if prompt_yes_no "Install and enable lora-sender as a boot service?" "y"; then
    bash "$repo_dir/scripts/install_service.sh" sender \
      --source-port "$sender_source_port" \
      --lora-port "$sender_lora_port" \
      --source-baudrate "$sender_source_baudrate" \
      --lora-baudrate "$sender_lora_baudrate"
    sudo systemctl enable --now lora-sender
    sender_install_service="y"
  else
    sender_install_service="n"
  fi

  echo
  echo "Sender setup complete."
  echo "Source serial: ${sender_source_port} @ ${sender_source_baudrate}"
  echo "LoRa serial: ${sender_lora_port} @ ${sender_lora_baudrate}"
  if [[ "$sender_install_service" == "y" ]]; then
    echo "Service: lora-sender"
  else
    echo "Service: not installed"
    echo "Run manually with: .venv/bin/python sender_bridge_app.py --source-port ${sender_source_port} --lora-port ${sender_lora_port} --source-baudrate ${sender_source_baudrate} --lora-baudrate ${sender_lora_baudrate}"
  fi
}

[[ $# -eq 0 ]] || {
  case "${1:-}" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "setup.sh is interactive only. Run with no arguments."
      ;;
  esac
}

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

echo "eChook LoRa setup wizard"
echo "Repository: $repo_dir"
echo

sudo -v

role_choice="$(prompt_choice "Choose this Pi's role:" "Receiver Pi" "Sender Pi")"
reboot_recommended="n"

case "$role_choice" in
  1) configure_receiver ;;
  2) configure_sender ;;
esac

echo
echo "Useful checks:"
echo "  sudo systemctl status lora-receiver --no-pager"
echo "  sudo systemctl status lora-sender --no-pager"

if [[ "$reboot_recommended" == "y" ]]; then
  if prompt_yes_no "Reboot now to apply networking changes?" "n"; then
    sudo reboot
  else
    echo "Reboot later with: sudo reboot"
  fi
fi
