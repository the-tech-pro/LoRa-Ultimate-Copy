#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/install_receiver_networking.sh hotspot [--wlan wlan0] [--address 192.168.50.1] [--dhcp-start 192.168.50.20] [--dhcp-end 192.168.50.150] [--channel 6] [--country US] [--ssid egr-echook] [--passphrase Florence!] [--port 5000]
  ./scripts/install_receiver_networking.sh ethernet [--eth eth0] [--address 192.168.7.1] [--dhcp-start 192.168.7.20] [--dhcp-end 192.168.7.150] [--port 5000]

This script configures receiver-side local dashboard networking in one place.

Modes:
  hotspot   Make the receiver Pi broadcast its own Wi-Fi network for the dashboard.
  ethernet  Make the receiver Pi serve the dashboard over a direct wired Ethernet link.

Examples:
  ./scripts/install_receiver_networking.sh ethernet
  ./scripts/install_receiver_networking.sh hotspot
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

validate_ipv4() {
  local value="$1"
  [[ "$value" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1

  local octet
  IFS='.' read -r -a octets <<<"$value"
  for octet in "${octets[@]}"; do
    [[ "$octet" =~ ^[0-9]{1,3}$ ]] || return 1
    (( octet >= 0 && octet <= 255 )) || return 1
  done
}

replace_managed_block() {
  local path="$1"
  local begin_marker="$2"
  local end_marker="$3"
  local body="$4"
  local tmp_file
  tmp_file="$(mktemp)"

  if sudo test -f "$path"; then
    sudo awk -v begin="$begin_marker" -v end="$end_marker" '
      $0 == begin { skip=1; next }
      $0 == end { skip=0; next }
      !skip { print }
    ' "$path" >"$tmp_file"
  else
    : >"$tmp_file"
  fi

  {
    cat "$tmp_file"
    printf '\n%s\n' "$begin_marker"
    printf '%s\n' "$body"
    printf '%s\n' "$end_marker"
  } >"${tmp_file}.new"

  sudo install -m 644 "${tmp_file}.new" "$path"
  rm -f "$tmp_file" "${tmp_file}.new"
}

remove_managed_block() {
  local path="$1"
  local begin_marker="$2"
  local end_marker="$3"
  local tmp_file
  tmp_file="$(mktemp)"

  if sudo test -f "$path"; then
    sudo awk -v begin="$begin_marker" -v end="$end_marker" '
      $0 == begin { skip=1; next }
      $0 == end { skip=0; next }
      !skip { print }
    ' "$path" >"$tmp_file"
    sudo install -m 644 "$tmp_file" "$path"
  fi

  rm -f "$tmp_file"
}

cleanup_hotspot_legacy() {
  remove_managed_block "/etc/dhcpcd.conf" "# BEGIN LORA RECEIVER AP" "# END LORA RECEIVER AP"
  remove_managed_block "/etc/default/hostapd" "# BEGIN LORA RECEIVER AP HOSTAPD" "# END LORA RECEIVER AP HOSTAPD"
  sudo rm -f /etc/hostapd/lora-receiver-ap.conf
  sudo rm -f /etc/dnsmasq.d/lora-receiver-ap.conf
  sudo rm -f /usr/local/bin/lora-receiver-ap-network.sh
  sudo rm -f /etc/systemd/system/lora-receiver-ap-network.service
  sudo systemctl disable --now hostapd dnsmasq lora-receiver-ap-network.service >/dev/null 2>&1 || true
  sudo nmcli connection delete lora-receiver-hotspot >/dev/null 2>&1 || true
}

cleanup_ethernet_legacy() {
  remove_managed_block "/etc/dhcpcd.conf" "# BEGIN LORA RECEIVER ETHERNET" "# END LORA RECEIVER ETHERNET"
  sudo rm -f /etc/dnsmasq.d/lora-receiver-ethernet.conf
  sudo nmcli connection delete lora-receiver-ethernet >/dev/null 2>&1 || true
}

cleanup_all_receiver_networking() {
  cleanup_hotspot_legacy
  cleanup_ethernet_legacy
  sudo systemctl daemon-reload
  sudo systemctl restart dnsmasq >/dev/null 2>&1 || true
  sudo systemctl restart dhcpcd >/dev/null 2>&1 || true
}

configure_hotspot_with_hostapd() {
  local hostapd_conf="/etc/hostapd/lora-receiver-ap.conf"
  local dnsmasq_conf="/etc/dnsmasq.d/lora-receiver-ap.conf"
  local network_script="/usr/local/bin/lora-receiver-ap-network.sh"
  local network_service="/etc/systemd/system/lora-receiver-ap-network.service"
  local ip_command
  local rfkill_command

  ip_command="$(command -v ip || true)"
  rfkill_command="$(command -v rfkill || true)"

  [[ -n "$ip_command" ]] || die "The 'ip' command is required"
  [[ -n "$rfkill_command" ]] || rfkill_command="true"

  echo "Using hostapd/dnsmasq hotspot setup"
  sudo apt update
  sudo apt install -y hostapd dnsmasq

  replace_managed_block \
    "/etc/dhcpcd.conf" \
    "# BEGIN LORA RECEIVER AP" \
    "# END LORA RECEIVER AP" \
    "denyinterfaces ${wlan}"

  sudo tee "$hostapd_conf" >/dev/null <<EOF
country_code=${country}
interface=${wlan}
driver=nl80211
ctrl_interface=/var/run/hostapd
ssid=${ssid}
hw_mode=g
channel=${channel}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${passphrase}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

  replace_managed_block \
    "/etc/default/hostapd" \
    "# BEGIN LORA RECEIVER AP HOSTAPD" \
    "# END LORA RECEIVER AP HOSTAPD" \
    "DAEMON_CONF=\"${hostapd_conf}\""

  sudo tee "$dnsmasq_conf" >/dev/null <<EOF
interface=${wlan}
bind-dynamic
domain-needed
bogus-priv
dhcp-range=${dhcp_start},${dhcp_end},255.255.255.0,24h
address=/dashboard.lora/${address}
EOF

  sudo tee "$network_script" >/dev/null <<EOF
#!/usr/bin/env bash
set -euo pipefail

${rfkill_command} unblock wlan || true
${ip_command} link set ${wlan} down || true
${ip_command} addr flush dev ${wlan} || true
${ip_command} addr add ${address}/24 dev ${wlan}
${ip_command} link set ${wlan} up
EOF
  sudo chmod 755 "$network_script"

  sudo tee "$network_service" >/dev/null <<EOF
[Unit]
Description=eChook LoRa receiver AP static address
After=network-pre.target
Before=hostapd.service dnsmasq.service
Wants=network-pre.target
ConditionPathExists=/sys/class/net/${wlan}

[Service]
Type=oneshot
ExecStart=${network_script}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl unmask hostapd >/dev/null 2>&1 || true
  sudo systemctl disable --now wpa_supplicant.service >/dev/null 2>&1 || true
  sudo systemctl disable --now "wpa_supplicant@${wlan}.service" >/dev/null 2>&1 || true
  sudo systemctl restart dhcpcd >/dev/null 2>&1 || true
  sudo systemctl enable --now lora-receiver-ap-network.service
  sudo systemctl enable --now hostapd dnsmasq
  sudo systemctl restart hostapd dnsmasq
}

configure_hotspot_with_networkmanager() {
  echo "Using NetworkManager hotspot setup"

  sudo systemctl enable --now NetworkManager >/dev/null 2>&1 || true
  sudo nmcli radio wifi on
  sudo nmcli device set "$wlan" managed yes >/dev/null 2>&1 || true
  sudo nmcli device disconnect "$wlan" >/dev/null 2>&1 || true
  sudo nmcli connection delete lora-receiver-hotspot >/dev/null 2>&1 || true
  sudo nmcli connection add type wifi ifname "$wlan" con-name lora-receiver-hotspot ssid "$ssid" autoconnect yes
  sudo nmcli connection modify lora-receiver-hotspot \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel "$channel" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$passphrase" \
    ipv4.method shared \
    ipv4.addresses "${address}/24" \
    ipv4.shared-dhcp-range "${dhcp_start},${dhcp_end}" \
    ipv6.method disabled \
    connection.autoconnect yes \
    connection.autoconnect-priority 100
  sudo nmcli connection up lora-receiver-hotspot
}

configure_ethernet_with_networkmanager() {
  echo "Using NetworkManager direct Ethernet setup"

  sudo systemctl enable --now NetworkManager >/dev/null 2>&1 || true
  sudo nmcli device set "$ethernet" managed yes >/dev/null 2>&1 || true
  sudo nmcli device disconnect "$ethernet" >/dev/null 2>&1 || true
  sudo nmcli connection add type ethernet ifname "$ethernet" con-name lora-receiver-ethernet autoconnect yes
  sudo nmcli connection modify lora-receiver-ethernet \
    ipv4.method shared \
    ipv4.addresses "${address}/24" \
    ipv4.shared-dhcp-range "${dhcp_start},${dhcp_end}" \
    ipv6.method disabled \
    connection.autoconnect yes \
    connection.autoconnect-priority 100
  sudo nmcli connection up lora-receiver-ethernet
}

configure_ethernet_with_dhcpcd() {
  local dnsmasq_conf="/etc/dnsmasq.d/lora-receiver-ethernet.conf"

  echo "Using dhcpcd/dnsmasq direct Ethernet setup"
  sudo apt update
  sudo apt install -y dnsmasq

  replace_managed_block \
    "/etc/dhcpcd.conf" \
    "# BEGIN LORA RECEIVER ETHERNET" \
    "# END LORA RECEIVER ETHERNET" \
    "interface ${ethernet}
static ip_address=${address}/24
static domain_name_servers=${address}"

  sudo tee "$dnsmasq_conf" >/dev/null <<EOF
interface=${ethernet}
bind-dynamic
domain-needed
bogus-priv
dhcp-range=${dhcp_start},${dhcp_end},255.255.255.0,24h
dhcp-option=6,${address}
EOF

  sudo systemctl restart dhcpcd >/dev/null 2>&1 || true
  sudo systemctl enable --now dnsmasq
  sudo systemctl restart dnsmasq
}

install_hotspot_mode() {
  [[ ${#passphrase} -ge 8 && ${#passphrase} -le 63 ]] || die "WPA2 passphrase must be between 8 and 63 characters"
  [[ "$country" =~ ^[A-Z]{2}$ ]] || die "--country must be a 2-letter uppercase country code such as US"
  [[ "$channel" =~ ^[0-9]+$ ]] || die "--channel must be a number"
  validate_ipv4 "$address" || die "--address must be a valid IPv4 address"
  validate_ipv4 "$dhcp_start" || die "--dhcp-start must be a valid IPv4 address"
  validate_ipv4 "$dhcp_end" || die "--dhcp-end must be a valid IPv4 address"

  cleanup_all_receiver_networking

  if command -v nmcli >/dev/null 2>&1 && sudo systemctl cat NetworkManager >/dev/null 2>&1; then
    configure_hotspot_with_networkmanager
  else
    configure_hotspot_with_hostapd
  fi

  echo
  echo "Receiver hotspot configured."
  echo "SSID: ${ssid}"
  echo "Password: ${passphrase}"
  echo "Dashboard URL: http://${address}:${dashboard_port}"
  echo "Extra DNS name: http://dashboard.lora:${dashboard_port}"
  echo
  echo "${wlan} is now dedicated to hotspot mode."
}

install_ethernet_mode() {
  validate_ipv4 "$address" || die "--address must be a valid IPv4 address"
  validate_ipv4 "$dhcp_start" || die "--dhcp-start must be a valid IPv4 address"
  validate_ipv4 "$dhcp_end" || die "--dhcp-end must be a valid IPv4 address"

  cleanup_all_receiver_networking

  if command -v nmcli >/dev/null 2>&1 && sudo systemctl cat NetworkManager >/dev/null 2>&1; then
    configure_ethernet_with_networkmanager
  else
    configure_ethernet_with_dhcpcd
  fi

  echo
  echo "Receiver direct Ethernet configured."
  echo "Ethernet interface: ${ethernet}"
  echo "Receiver IP: ${address}"
  echo "Dashboard URL: http://${address}:${dashboard_port}"
  echo
  echo "Connect the client device through an Ethernet adapter to ${ethernet} and keep the Pi on normal power."
}

[[ $# -ge 1 ]] || {
  usage
  exit 1
}

mode="$1"
shift

wlan="wlan0"
ethernet="eth0"
address=""
dhcp_start=""
dhcp_end=""
channel="6"
country="US"
ssid="egr-echook"
passphrase="Florence!"
dashboard_port="5000"

case "$mode" in
  hotspot)
    address="192.168.50.1"
    dhcp_start="192.168.50.20"
    dhcp_end="192.168.50.150"

    while [[ $# -gt 0 ]]; do
      case "$1" in
        --wlan)
          require_value "$1" "${2:-}"
          wlan="$2"
          shift 2
          ;;
        --address)
          require_value "$1" "${2:-}"
          address="$2"
          shift 2
          ;;
        --dhcp-start)
          require_value "$1" "${2:-}"
          dhcp_start="$2"
          shift 2
          ;;
        --dhcp-end)
          require_value "$1" "${2:-}"
          dhcp_end="$2"
          shift 2
          ;;
        --channel)
          require_value "$1" "${2:-}"
          channel="$2"
          shift 2
          ;;
        --country)
          require_value "$1" "${2:-}"
          country="$2"
          shift 2
          ;;
        --ssid)
          require_value "$1" "${2:-}"
          ssid="$2"
          shift 2
          ;;
        --passphrase)
          require_value "$1" "${2:-}"
          passphrase="$2"
          shift 2
          ;;
        --port)
          require_value "$1" "${2:-}"
          dashboard_port="$2"
          shift 2
          ;;
        -h|--help)
          usage
          exit 0
          ;;
        *)
          die "Unknown hotspot option: $1"
          ;;
      esac
    done
    ;;
  ethernet)
    address="192.168.7.1"
    dhcp_start="192.168.7.20"
    dhcp_end="192.168.7.150"

    while [[ $# -gt 0 ]]; do
      case "$1" in
        --eth)
          require_value "$1" "${2:-}"
          ethernet="$2"
          shift 2
          ;;
        --address)
          require_value "$1" "${2:-}"
          address="$2"
          shift 2
          ;;
        --dhcp-start)
          require_value "$1" "${2:-}"
          dhcp_start="$2"
          shift 2
          ;;
        --dhcp-end)
          require_value "$1" "${2:-}"
          dhcp_end="$2"
          shift 2
          ;;
        --port)
          require_value "$1" "${2:-}"
          dashboard_port="$2"
          shift 2
          ;;
        -h|--help)
          usage
          exit 0
          ;;
        *)
          die "Unknown ethernet option: $1"
          ;;
      esac
    done
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    die "Mode must be 'hotspot' or 'ethernet'"
    ;;
esac

[[ "$dashboard_port" =~ ^[0-9]+$ ]] || die "--port must be a number"

case "$mode" in
  hotspot)
    install_hotspot_mode
    ;;
  ethernet)
    install_ethernet_mode
    ;;
esac

echo "If you have not already installed the receiver service, run:"
echo "  bash ./scripts/install_service.sh receiver --serial-port /dev/ttyS0 --baudrate 9600 --host 0.0.0.0 --port ${dashboard_port}"
echo
echo "A reboot is recommended after changing receiver networking:"
echo "  sudo reboot"
