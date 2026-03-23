# eChook LoRa Telemetry Dashboard

This project replaces the eChook Bluetooth link with a LoRa link while keeping the original 5-byte eChook telemetry packet format unchanged.

The default architecture from [PRD.md](PRD.md) is:

```text
eChook -> UART -> USB-to-UART adapter -> USB -> Sender Raspberry Pi -> UART -> LoRa -> air -> LoRa -> Receiver Raspberry Pi -> Flask dashboard
```

The simpler fallback architecture is:

```text
eChook -> UART -> LoRa -> air -> LoRa -> Receiver Raspberry Pi -> Flask dashboard
```

## Table of Contents

- [Overview](#overview)
- [Install](#install)
- [Setup Wizard](#setup-wizard)
- [Receiver Pi Setup](#receiver-pi-setup)
- [Receiver Networking](#receiver-networking)
- [Sender Pi Setup](#sender-pi-setup)
- [Manual Run](#manual-run)
- [Services](#services)
- [Update](#update)
- [Troubleshooting](#troubleshooting)
- [Repository Layout](#repository-layout)

## Overview

### What runs where

Receiver Pi:

- always runs the dashboard and packet decoder
- reads LoRa UART bytes from the receiver-side SX1268 HAT
- reconstructs and validates 5-byte eChook packets
- decodes telemetry values
- adds the authoritative receiver timestamp
- serves the local Flask dashboard
- renders `Live`, `Recordings`, `Storage`, and `Settings` views
- supports named recordings, lap markers, recording playback, raw/CSV downloads, and storage management
- keeps the live page separate from saved-recording playback

Sender Pi:

- is used in the default architecture only
- reads raw 5-byte telemetry packets from the eChook UART
- in the current setup, receives the eChook feed through a USB-to-UART adapter plugged into the sender Pi
- uses the Pi UART on the GPIO header to talk to the sender-side SX1268 HAT
- validates framing and forwards valid packets over LoRa

Direct fallback:

- if you wire the eChook directly to the sender-side LoRa radio, you do not run any Python code on the sender side
- the receiver Pi setup stays the same
- the LoRa radios must behave like a transparent serial bridge

### Current Working Bench Setup

Receiver Pi:

- SX1268 LoRa HAT on Raspberry Pi GPIO header
- receiver LoRa UART device: `/dev/ttyS0`
- receiver LoRa baudrate: `9600`
- dashboard command: `receiver_app.py`

Sender Pi:

- eChook UART into USB-to-UART adapter
- USB adapter appears as `/dev/ttyUSB0`
- eChook source baudrate: `115200`
- sender-side SX1268 LoRa HAT on Raspberry Pi GPIO header
- sender LoRa UART device: `/dev/ttyS0`
- sender LoRa baudrate: `9600`
- sender command: `sender_bridge_app.py`

### LoRa Link Notes

- the eChook UART and SX1268 HAT UART are separate serial links on the sender Pi and do not have to use the same baudrate
- the sender bridge does not change packet meaning
- to stay within the practical LoRa link budget, the sender bridge keeps only the latest validated packet per telemetry ID and flushes those latest packets on a short interval
- this is a Phase 3 hardening step and stays within the PRD
- the live dashboard still keeps only a small in-memory recent sample window for the selectable live graph
- persistent telemetry is written only while an operator-started recording is active
- recordings are stored on the receiver Pi and can later be replayed through a dashboard page that mirrors the live view

### Dashboard Tabs

- the main dashboard uses a sidebar to switch between receiver pages quickly without mixing live data and saved playback state
- `Live` shows the current receiver telemetry, recording status, live graph, and start/stop/lap controls
- `Recordings` lists saved recordings and links into the dedicated playback page for each session
- `Storage` shows total disk space, free space, recording usage, quota, and cleanup controls
- `Settings` stores recording naming and storage defaults on the receiver Pi, including the default 4 GB recording quota for new installs

## Install

These steps apply to both Pis unless noted otherwise.

### One-Command Install

If the repo is not cloned yet, use:

```bash
curl -fsSL https://raw.githubusercontent.com/the-tech-pro/LoRa-Ultimate-Copy/main/install.sh | bash
```

That command will:

- fetch the bootstrap installer
- clone or update the repo in `~/LoRa-Ultimate-Copy`
- launch the interactive setup wizard

If cloning finishes and you do not immediately see the setup wizard prompts, run:

```bash
cd ~/LoRa-Ultimate-Copy
bash ./scripts/setup.sh
```

You can still use the manual steps below if you want tighter control.

<details>
<summary>Manual Install (Advanced)</summary>

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 2. Clone the repo

```bash
git clone https://github.com/the-tech-pro/LoRa-Ultimate-Copy
cd LoRa-Ultimate-Copy
```

### 3. Create the virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. What `.venv` is

`.venv` is a project-local Python environment. It keeps this project's Python packages separate from the rest of the Pi.

While it is active:

- `python` means the Python interpreter inside this project
- `pip` installs packages into this project only

You do not have to keep the virtual environment active all the time, but you do need to use it when installing packages or running this project's Python commands.

Activate it:

```bash
source .venv/bin/activate
```

Or call the venv Python directly without activating it:

```bash
.venv/bin/python receiver_app.py --help
```

Leave the virtual environment with:

```bash
deactivate
```

</details>

## Setup Wizard

If the repo is already cloned, use:

```bash
cd ~/LoRa-Ultimate-Copy
bash ./scripts/setup.sh
```

The wizard will:

- install system packages
- create or reuse `.venv`
- install Python dependencies
- detect whether the Pi hostname looks like `sender` or `receiver`, ask for confirmation, and fall back to a manual role choice if needed
- detect likely serial devices from the Pi UART and attached USB serial adapters, then ask for confirmation instead of requiring raw device names up front
- prefer the current bench defaults during serial detection: receiver/sender LoRa on `/dev/ttyS0`, sender source on `/dev/ttyUSB0`
- present the remaining default values as `y/n` confirmation prompts, and only ask for manual text entry if you reject the default
- ask whether to install the correct `systemd` service, with `yes` as the default
- recommend a reboot when you choose the Pi's on-board UART for LoRa
- for the receiver, optionally configure `ethernet`, `hotspot`, or leave networking unchanged

Recommended choices:

- receiver Pi on a Pi 4 B with iPad or laptop access: choose `Receiver Pi`, then `Direct Ethernet`
- sender Pi in the car: choose `Sender Pi`

The wizard uses the existing installer scripts underneath:

- [install_service.sh](C:/Users/maxdu/Documents/Code%20Projects/Active/LoRa%20Ultimate%20Copy/scripts/install_service.sh)
- [install_receiver_networking.sh](C:/Users/maxdu/Documents/Code%20Projects/Active/LoRa%20Ultimate%20Copy/scripts/install_receiver_networking.sh)

## Receiver Pi Setup

### Hardware

In the current setup, the receiver-side SX1268 LoRa HAT is mounted directly on the Raspberry Pi GPIO header.

That means:

- the receiver LoRa link is not a USB serial device in the normal Pi setup
- the HAT is controlled through the Pi UART on the GPIO header
- the current bench setup uses `/dev/ttyS0` for the receiver-side SX1268 HAT UART

Do not use `/dev/ttyUSB0` for the receiver unless you are intentionally using the HAT's USB-to-UART path instead of the Raspberry Pi GPIO/UART path.

### HAT Configuration

1. Put the UART selection jumper on `B` so the LoRa module is controlled by the Raspberry Pi.
2. Put the module in transmission mode by setting `M0` low and `M1` low.
3. Enable the Raspberry Pi serial port:

```bash
sudo raspi-config
```

Then choose:

- `Interface Options` -> `Serial Port`
- `Login shell over serial` -> `No`
- `Enable serial hardware` -> `Yes`

4. Reboot:

```bash
sudo reboot
```

5. After reboot, confirm the UART device:

```bash
ls -l /dev/serial*
ls -l /dev/ttyS0 /dev/ttyAMA0 2>/dev/null
```

In the current bench setup, use `/dev/ttyS0`.

### Run the Receiver App

```bash
cd ~/LoRa-Ultimate-Copy
source .venv/bin/activate
python3 receiver_app.py --serial-port /dev/ttyS0 --baudrate 9600 --host 0.0.0.0 --port 5000 --data-dir data
```

Then open the dashboard from another device on the same network:

```text
http://<receiver-pi-ip>:5000
```

The receiver will create its settings and recordings under the `data/` directory you pass in.

## Receiver Networking

Use a single script for receiver-side dashboard networking:

- [install_receiver_networking.sh](C:/Users/maxdu/Documents/Code%20Projects/Active/LoRa%20Ultimate%20Copy/scripts/install_receiver_networking.sh)

For most users, [setup.sh](C:/Users/maxdu/Documents/Code%20Projects/Active/LoRa%20Ultimate%20Copy/scripts/setup.sh) is the easier path.
Use `install_receiver_networking.sh` directly only if you are changing receiver networking after initial setup.

This stays inside the PRD:

- the dashboard is still local-only
- the receiver Pi still hosts the Flask dashboard
- no cloud or internet service is required for dashboard access

Available modes:

- `ethernet` for a direct wired connection to a laptop or iPad
- `hotspot` for a dedicated Wi-Fi network from the receiver Pi

### Ethernet Mode

For a Raspberry Pi 4 B, direct wired Ethernet is the more reliable way to connect an iPad or laptop to the dashboard.

What this changes:

- the receiver Pi uses its built-in `eth0` port
- the directly connected client gets an IP on that cable link
- the dashboard is reachable at `http://192.168.7.1:5000`
- this does not use Raspberry Pi USB gadget mode

Install it:

```bash
cd ~/LoRa-Ultimate-Copy
bash ./scripts/install_receiver_networking.sh ethernet
sudo reboot
```

Default Ethernet values:

- receiver Ethernet IP: `192.168.7.1`
- client DHCP range: `192.168.7.20` to `192.168.7.150`
- dashboard URL: `http://192.168.7.1:5000`

Useful optional flags:

```bash
bash ./scripts/install_receiver_networking.sh ethernet \
  --eth eth0 \
  --address 192.168.7.1 \
  --dhcp-start 192.168.7.20 \
  --dhcp-end 192.168.7.150 \
  --port 5000
```

How to use it with an iPad or laptop:

1. Power the receiver Pi from its normal power supply.
2. Connect the client device through a USB-C to Ethernet adapter.
3. Connect that adapter to the receiver Pi `eth0` port with a normal Ethernet cable.
4. Open `http://192.168.7.1:5000`.

Important:

- for a Pi 4 B, this is the preferred wired path instead of USB gadget mode
- direct Ethernet does not depend on Wi-Fi hotspot mode
- the dashboard works over this link because the receiver app already binds to `0.0.0.0`

### Hotspot Mode

Use this if you want the receiver Pi to be the only Wi-Fi network for the dashboard.

What this changes:

- `wlan0` becomes a dedicated receiver hotspot
- the receiver Pi serves the dashboard at `http://192.168.50.1:5000`
- normal Wi-Fi client mode on `wlan0` is turned off
- on Raspberry Pi OS Bookworm and newer, the script uses NetworkManager for the hotspot
- on older Pi OS images, the script falls back to `hostapd` and `dnsmasq`

Install it:

```bash
cd ~/LoRa-Ultimate-Copy
bash ./scripts/install_receiver_networking.sh hotspot
sudo reboot
```

Default hotspot values:

- SSID: `egr-echook`
- password: `Florence!`
- receiver hotspot IP: `192.168.50.1`
- dashboard URL: `http://192.168.50.1:5000`
- extra local DNS name: `http://dashboard.lora:5000`

These are now hardcoded in [install_receiver_networking.sh](C:/Users/maxdu/Documents/Code%20Projects/Active/LoRa%20Ultimate%20Copy/scripts/install_receiver_networking.sh).
If you want to change them later, edit the `ssid` and `passphrase` values in that file.

Useful optional flags:

```bash
bash ./scripts/install_receiver_networking.sh hotspot \
  --ssid "egr-echook" \
  --passphrase "Florence!" \
  --country US \
  --wlan wlan0 \
  --address 192.168.50.1 \
  --dhcp-start 192.168.50.20 \
  --dhcp-end 192.168.50.150 \
  --channel 6 \
  --port 5000
```

After reboot:

1. Connect your phone or laptop to the receiver Pi SSID.
2. Start or enable the receiver app if it is not already running.
3. Open `http://192.168.50.1:5000`.

Important:

- hotspot mode is for the receiver Pi only
- hotspot mode does not change the LoRa UART setup
- with AP-only Wi-Fi, repo updates need Ethernet or another separate internet path

## Sender Pi Setup

### Hardware

The sender Pi sits between the eChook and the sender-side LoRa radio.

In the current setup:

- the eChook UART is connected to a USB-to-UART adapter
- that adapter is plugged into the sender Pi over USB
- the sender app reads eChook telemetry from the USB serial device on the Pi
- the sender-side SX1268 LoRa HAT is mounted on the sender Pi GPIO header and uses the Pi UART
- the HAT USB connection is not used for the sender LoRa link in this setup

Expected signal flow:

```text
eChook UART -> USB-to-UART adapter -> USB -> Sender Pi serial input
Sender Pi UART on GPIO header -> SX1268 LoRa HAT
```

Typical device names:

- eChook side via USB adapter: `/dev/ttyUSB0`
- LoRa side via SX1268 HAT: `/dev/ttyS0`

### Run the Sender Bridge

```bash
cd ~/LoRa-Ultimate-Copy
source .venv/bin/activate
python3 sender_bridge_app.py --source-port /dev/ttyUSB0 --lora-port /dev/ttyS0 --source-baudrate 115200 --lora-baudrate 9600
```

Important:

- `source-baudrate` must match the real eChook UART output
- `lora-baudrate` must match the SX1268 HAT UART setting
- in the current working bench setup, that is `115200` on the eChook side and `9600` on the LoRa side

## Manual Run

Use this order when starting manually:

1. Start the receiver Pi app first.
2. Start the sender Pi bridge second.
3. Open the dashboard from the receiver Pi.

Known-good bench commands:

Receiver:

```bash
cd ~/LoRa-Ultimate-Copy
source .venv/bin/activate
python3 receiver_app.py --serial-port /dev/ttyS0 --baudrate 9600 --host 0.0.0.0 --port 5000
```

Sender:

```bash
cd ~/LoRa-Ultimate-Copy
source .venv/bin/activate
python3 sender_bridge_app.py --source-port /dev/ttyUSB0 --lora-port /dev/ttyS0 --source-baudrate 115200 --lora-baudrate 9600
```

If your eChook UART is not actually `115200`, change only `--source-baudrate` to the real eChook baud. Keep the receiver `--baudrate` and sender `--lora-baudrate` matched to the SX1268 module UART setting.

## Services

If you want the apps to start automatically on boot and restart after a crash, install them as `systemd` services.

The generated services now:

- wait for the configured serial devices
- wait for `systemd-udev-settle.service`
- add a short startup delay at boot
- ensure the service user has `dialout` access for Raspberry Pi UART and USB serial devices
- disable the Raspberry Pi serial console and enable serial hardware automatically when you use on-board UART devices such as `/dev/ttyS0`

That helps with Raspberry Pi boot cases where the USB UART or Pi UART is not fully settled yet during early boot.

### Install Receiver Service

```bash
cd ~/LoRa-Ultimate-Copy
bash ./scripts/install_service.sh receiver --serial-port /dev/ttyS0 --baudrate 9600 --host 0.0.0.0 --port 5000
sudo systemctl enable --now lora-receiver
```

### Install Sender Service

```bash
cd ~/LoRa-Ultimate-Copy
bash ./scripts/install_service.sh sender --source-port /dev/ttyUSB0 --lora-port /dev/ttyS0 --source-baudrate 115200 --lora-baudrate 9600
sudo systemctl enable --now lora-sender
```

### Useful Service Commands

```bash
sudo systemctl status lora-receiver --no-pager
sudo systemctl status lora-sender --no-pager
sudo systemctl restart lora-receiver
sudo systemctl restart lora-sender
sudo systemctl stop lora-receiver
sudo systemctl stop lora-sender
sudo systemctl disable lora-receiver
sudo systemctl disable lora-sender
```

## Update

### Manual Update

If you are not using services yet:

```bash
cd ~/LoRa-Ultimate-Copy
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
```

### One-Command Update

If the Pi repo was cloned with Git:

```bash
cd ~/LoRa-Ultimate-Copy
bash ./scripts/update_lora.sh
```

What `update_lora.sh` does:

- stops if tracked repo files have local changes
- runs `git pull --ff-only`
- installs Python dependencies from `requirements.txt`
- restarts `lora-sender` and/or `lora-receiver` if those `systemd` service files are installed

Important:

- if you change the service command itself, such as serial port or baudrate, rerun `install_service.sh` before `update_lora.sh`
- if `install_service.sh` itself changes, rerun it on the Pi so the latest unit-file behavior is installed

## Troubleshooting

### Restart the Services

Receiver:

```bash
sudo systemctl restart lora-receiver
```

Sender:

```bash
sudo systemctl restart lora-sender
```

Restart both:

```bash
sudo systemctl restart lora-receiver
sudo systemctl restart lora-sender
```

### Check Whether the Services Are Running

Receiver:

```bash
sudo systemctl status lora-receiver --no-pager
```

Sender:

```bash
sudo systemctl status lora-sender --no-pager
```

You want to see `active (running)`.

### Check Whether the Services Will Start at Boot

Receiver:

```bash
sudo systemctl is-enabled lora-receiver
```

Sender:

```bash
sudo systemctl is-enabled lora-sender
```

You want to see `enabled`.

### Check the Exact Command Each Service Is Using

Receiver:

```bash
sudo systemctl cat lora-receiver
pgrep -af receiver_app.py
```

Sender:

```bash
sudo systemctl cat lora-sender
pgrep -af sender_bridge_app.py
```

For the current bench setup, the running commands should include:

- receiver: `--serial-port /dev/ttyS0 --baudrate 9600`
- sender: `--source-port /dev/ttyUSB0 --lora-port /dev/ttyS0 --source-baudrate 115200 --lora-baudrate 9600`

### Check Recent Logs

Receiver:

```bash
journalctl -u lora-receiver -n 50 --no-pager
```

Sender:

```bash
journalctl -u lora-sender -n 50 --no-pager
```

To follow new logs live:

```bash
journalctl -u lora-receiver -f
journalctl -u lora-sender -f
```

If `journalctl -f` shows nothing, that does not automatically mean the service is stopped. It can also mean the service is running but has not written a new log line yet. Use `systemctl status` and `pgrep -af` to confirm whether it is currently running.

### Common Causes of No Dashboard Updates

- wrong serial device
- wrong baudrate on the eChook side or LoRa side
- service user missing permission to open `/dev/ttyS0`, `/dev/ttyUSB0`, or `/dev/ttyACM0`
- Pi serial login shell still enabled
- HAT jumpers not set correctly for Raspberry Pi UART control
- SX1268 modules not sharing the same `NETID`, channel, or air speed
- fixed-point transmission or RSSI output enabled on the LoRa modules
- sender service starting too early at boot before serial devices settle

If the services only work after a manual restart but not immediately after boot, reinstall them with `install_service.sh` and reboot again.

If the sender logs warnings like `LoRa UART write timed out`, the LoRa-side serial link is overloaded or stalled. That points to the sender-to-LoRa path, not the Flask dashboard.

If you see `Permission denied` opening `/dev/ttyS0` or another serial device, rerun `install_service.sh` for that Pi and restart the service. The installer now adds the service user to `dialout` automatically.

### Check Receiver Networking

If you installed receiver hotspot mode, these commands should help:

```bash
sudo systemctl status lora-receiver-ap-network --no-pager
sudo systemctl status hostapd --no-pager
sudo systemctl status dnsmasq --no-pager
ip addr show wlan0
```

You want to see:

- `lora-receiver-ap-network`, `hostapd`, and `dnsmasq` active
- `wlan0` holding `192.168.50.1/24` unless you chose a different address

If you installed receiver direct Ethernet mode, these commands should help:

```bash
nmcli connection show --active
ip addr show eth0
sudo systemctl status dnsmasq --no-pager
```

You want to see:

- `eth0` holding `192.168.7.1/24` unless you chose a different address
- either a NetworkManager Ethernet profile active or `dnsmasq` active on older Pi OS images

## Repository Layout

```text
install.sh             Bootstrap installer that clones the repo and runs setup.sh
receiver_app.py         Receiver Pi entrypoint
sender_bridge_app.py    Sender Pi entrypoint
echook_lora/
  constants.py          Packet constants and telemetry metadata
  protocol.py           Raw packet validation and decode logic
  receiver.py           Receiver-side LoRa UART reader
  recordings.py         Receiver-side recordings, playback, settings, and storage logic
  sender_bridge.py      Sender-side UART-to-LoRa bridge
  state.py              Latest telemetry store and derived status
  dashboard.py          Flask dashboard pages and JSON endpoints
  templates/            Live dashboard and recording playback templates
scripts/
  setup.sh              Interactive one-command sender/receiver setup wizard
  install_service.sh    Create a sender or receiver systemd service
  install_receiver_networking.sh  Configure receiver Pi hotspot or direct Ethernet access
  update_lora.sh        Pull latest code, install deps, and restart services
tests/
  test_dashboard_api.py Dashboard route smoke tests when Flask is installed
  test_protocol.py      Decoder and packet validation tests
  test_recordings.py    Recording lifecycle, playback, and storage tests
  test_streams.py       Sender/receiver stream handling tests
```
