# eChook LoRa Telemetry Dashboard

This project replaces the eChook Bluetooth link with a LoRa link while keeping the original 5-byte eChook telemetry packet format unchanged.

The default architecture from `PRD.md` is:

```text
eChook -> UART -> USB-to-UART adapter -> USB -> Sender Raspberry Pi -> UART -> LoRa -> air -> LoRa -> Receiver Raspberry Pi -> Flask dashboard
```

The simpler fallback architecture is:

```text
eChook -> UART -> LoRa -> air -> LoRa -> Receiver Raspberry Pi -> Flask dashboard
```

## Which code goes on which Raspberry Pi

### Receiver Raspberry Pi

The receiver Pi always runs the dashboard and packet decoder.

Files used on the receiver Pi:

- `receiver_app.py`
- `echook_lora/receiver.py`
- `echook_lora/protocol.py`
- `echook_lora/state.py`
- `echook_lora/dashboard.py`
- `echook_lora/constants.py`

What it does:

- reads raw telemetry bytes from the receiver-side LoRa module over UART,
- reconstructs and validates 5-byte eChook packets,
- decodes telemetry values using the eChook encoding rules,
- adds the authoritative receiver timestamp,
- stores the latest value for each telemetry ID,
- serves the local Flask dashboard.

### Sender Raspberry Pi

The sender Pi is used in the default architecture only.

Files used on the sender Pi:

- `sender_bridge_app.py`
- `echook_lora/sender_bridge.py`
- `echook_lora/protocol.py`
- `echook_lora/constants.py`

What it does:

- reads raw 5-byte telemetry packets from the eChook UART,
- in the current setup, receives that eChook UART feed through a USB-to-UART adapter plugged into the sender Pi,
- uses the sender Pi UART on the GPIO header to talk to the sender-side SX1268 LoRa HAT,
- validates packet framing,
- forwards valid packets unchanged to the LoRa radio over UART.

### Direct eChook-to-LoRa fallback

If you wire the eChook directly to the sender-side LoRa radio, you do not run any Python code on the sender side.

In that fallback mode:

- the receiver Pi setup stays the same,
- `sender_bridge_app.py` is not used,
- the LoRa radios must behave like a transparent serial bridge.

## Repository layout

```text
receiver_app.py         Receiver Pi entrypoint
sender_bridge_app.py    Sender Pi entrypoint
echook_lora/
  constants.py          Packet constants and telemetry ID metadata
  protocol.py           Raw packet validation and decode logic
  receiver.py           Receiver-side LoRa UART reader
  sender_bridge.py      Sender-side UART-to-LoRa bridge
  state.py              Latest telemetry store and derived status
  dashboard.py          Flask dashboard and JSON endpoint
scripts/
  install_service.sh    Create a sender or receiver systemd service
  update_lora.sh        Pull latest code, install deps, and restart services
```

## Raspberry Pi setup

These steps apply to both Pis unless noted otherwise.

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 2. Copy the project onto the Pi

Clone the repo or copy this folder onto each Raspberry Pi that needs it.

Example:

```bash
git clone https://github.com/the-tech-pro/LoRa-Ultimate-Copy
cd LoRa-Ultimate-Copy
```

### 3. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. What `.venv` is and how to use it

`.venv` is a project-local Python environment. It keeps this project's Python packages separate from the rest of the Pi, so `flask` and `pyserial` are installed for this repo without affecting other projects.

When you run:

```bash
source .venv/bin/activate
```

your shell switches into that environment. You will usually see `(.venv)` appear at the start of the command prompt.

While it is active:

- `python` means the Python interpreter inside this project
- `pip` installs packages into this project only

You do not have to keep the virtual environment active all the time, but you do need to use it when installing packages or running this project's Python commands.

There are two valid ways to do that:

1. Activate it first:

```bash
source .venv/bin/activate
python receiver_app.py --help
```

2. Or call the venv Python directly without activating it:

```bash
.venv/bin/python receiver_app.py --help
```

If you activated it and want to leave it later, run:

```bash
deactivate
```

### 5. If you need to update the repo while still setting up

If you already cloned the repo and created `.venv`, update with:

```bash
cd ~/LoRa-Ultimate-Copy
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
```

If your shell is already showing `(.venv)`, you can skip the `source .venv/bin/activate` line.

If you prefer not to activate the environment, the same update can be done with:

```bash
cd ~/LoRa-Ultimate-Copy
git pull --ff-only
.venv/bin/pip install -r requirements.txt
```

## Receiver Pi setup and run

### Wiring

In the current setup, the receiver-side SX1268 LoRa HAT is mounted directly on the Raspberry Pi GPIO header.

That means:

- the receiver LoRa link is not a USB serial device in the normal Pi setup,
- the HAT is controlled through the Pi UART on the GPIO header,
- the current bench setup uses `/dev/ttyS0` for the receiver-side SX1268 HAT UART.

Do not use `/dev/ttyUSB0` for the receiver unless you are intentionally using the HAT's USB-to-UART path instead of the Raspberry Pi GPIO/UART path.

### Receiver HAT configuration

Before running the receiver app, check the SX1268 HAT setup:

1. Put the UART selection jumper on `B` so the LoRa module is controlled by the Raspberry Pi.
2. Put the module in transmission mode by setting `M0` low and `M1` low, which on the HAT means both jumpers fitted to short them.
3. Enable the Raspberry Pi serial port:

```bash
sudo raspi-config
```

Then choose:

- `Interface Options` -> `Serial Port`
- `Login shell over serial` -> `No`
- `Enable serial hardware` -> `Yes`

4. Reboot the Pi:

```bash
sudo reboot
```

5. After reboot, confirm which UART device the Pi selected:

```bash
ls -l /dev/serial*
ls -l /dev/ttyS0 /dev/ttyAMA0 2>/dev/null
```

In the current bench setup, use `/dev/ttyS0` for the receiver command. If your Pi maps the HAT UART differently, override it with the real device you found above.

You will need the correct Linux serial device, for example:

- `/dev/ttyAMA0`
- `/dev/ttyS0`
- `/dev/serial0`

### Run the receiver app

```bash
source .venv/bin/activate
python3 receiver_app.py --serial-port /dev/ttyS0 --baudrate 9600 --host 0.0.0.0 --port 5000
```

Important:

- the receiver-side SX1268 UART currently works at `9600` in the bench setup,
- the receiver app now defaults to `/dev/ttyS0` at `9600`,
- if you intentionally reconfigure both LoRa modules later, change `--baudrate` to match the new LoRa UART setting.

If you get `could not open port`, the most likely causes are:

- the selected serial port is wrong,
- the Pi serial port is not enabled yet,
- the serial login shell is still enabled,
- the HAT jumpers are not set for Raspberry Pi UART control.

Then open the dashboard from another device on the same network:

```text
http://<receiver-pi-ip>:5000
```

What you should see:

- connection status,
- latest packet age,
- speed,
- voltage,
- current,
- temperatures,
- a live table of the latest decoded packets.

## Sender Pi setup and run

### Wiring

The sender Pi sits between the eChook and the sender-side LoRa radio.

In the current setup:

- the eChook UART is connected to a USB-to-UART adapter,
- that adapter is plugged into the sender Pi over USB,
- the sender app reads the eChook telemetry from the USB serial device that appears on the Pi,
- the sender-side SX1268 LoRa HAT is mounted on the sender Pi GPIO header and uses the Pi UART,
- the HAT USB connection is not used for the sender LoRa link in this setup.

Expected signal flow:

```text
eChook UART -> USB-to-UART adapter -> USB -> Sender Pi serial input
Sender Pi UART on GPIO header -> SX1268 LoRa HAT
```

Use the actual serial device names for your sender Pi and attached radio.

Examples:

- eChook side via USB-to-UART adapter: `/dev/ttyUSB0`
- LoRa side through the SX1268 HAT on GPIO: `/dev/ttyS0` in the current bench setup, or `/dev/ttyAMA0` / `/dev/serial0` if your Pi is configured differently

### Run the sender bridge

```bash
source .venv/bin/activate
python3 sender_bridge_app.py --source-port /dev/ttyUSB0 --lora-port /dev/ttyS0 --source-baudrate 115200 --lora-baudrate 9600
```

Important:

- `source-baudrate` is the eChook side and must match the real eChook UART output,
- `lora-baudrate` is the SX1268 HAT UART side and must match the radio module UART setting,
- the current working setup is `--source-port /dev/ttyUSB0 --lora-port /dev/ttyS0 --source-baudrate 115200 --lora-baudrate 9600`,
- the sender app now defaults to `115200` for the eChook side and `9600` for the LoRa side,
- the sender app now defaults the SX1268 HAT LoRa port to `/dev/ttyS0`,
- if you intentionally reconfigure the SX1268 pair later, change only `--lora-baudrate` to match that new LoRa UART setting.

The sender bridge does not decode or transform packets. It validates framing and forwards valid 5-byte packets unchanged, which matches the PRD requirement to preserve the original eChook packet semantics.

## UART and LoRa notes

- The current code defaults to the working bench setup: `115200` for the eChook UART and `9600` for the SX1268 HAT UART.
- The eChook source UART and the SX1268 HAT UART are separate serial links on the sender Pi and do not have to use the same baudrate.
- The LoRa-side serial commands should use `9600` unless you intentionally reconfigure both SX1268 modules to a different UART baudrate.
- Revalidate the real eChook UART settings on the bench before final deployment.
- The LoRa pair should be configured so the radios act as a transparent serial link for this first version.
- This first version does not add a custom protocol, batching, or sender-side metadata.

For this project, both SX1268 modules should also be checked for:

- the same `NETID`,
- the same channel,
- the same air speed,
- transparent transmission enabled,
- fixed-point transmission disabled,
- RSSI byte disabled,
- transmission mode selected with `M0` low and `M1` low.

If the LoRa LEDs flash but the dashboard stays empty, the most likely causes are:

- the Pi is using the wrong serial device,
- the Pi UART is enabled but the module UART baud does not match,
- the sender is using the right `source-baudrate` for the eChook but the wrong `lora-baudrate` for the SX1268 HAT,
- the two HATs do not share the same channel, `NETID`, or air speed,
- fixed-point transmission or RSSI output is enabled, so the receiver no longer sees clean 5-byte eChook packets,
- the receiver is dropping invalid packets and logging warnings.

If you are running the receiver in the foreground, watch the terminal for dropped-packet warnings.

If you are running it as a service, use:

```bash
journalctl -u lora-receiver -f
```

The current known-good bench commands are:

```bash
source .venv/bin/activate
python3 receiver_app.py --serial-port /dev/ttyS0 --baudrate 9600 --host 0.0.0.0 --port 5000
```

and on the sender Pi:

```bash
source .venv/bin/activate
python3 sender_bridge_app.py --source-port /dev/ttyUSB0 --lora-port /dev/ttyS0 --source-baudrate 115200 --lora-baudrate 9600
```

If your eChook UART is not actually `115200`, change only `--source-baudrate` to the real eChook baud. Keep the receiver `--baudrate` and sender `--lora-baudrate` matched to the SX1268 module UART setting.

## Typical deployment plan

### Default architecture

1. Put the full repo on both Pis.
2. On the sender Pi, run `sender_bridge_app.py`.
3. On the receiver Pi, run `receiver_app.py`.
4. Open the Flask dashboard from the receiver Pi.

### Fallback architecture

1. Put the repo only on the receiver Pi.
2. Wire eChook directly to the sender-side LoRa module.
3. Run `receiver_app.py` on the receiver Pi.
4. Open the Flask dashboard from the receiver Pi.

## Optional: Run as services

If you want the apps to start automatically on boot and restart after a crash, install them as `systemd` services.

### Receiver Pi service

1. SSH into the receiver Pi and go to the repo:

```bash
cd ~/LoRa-Ultimate-Copy
```

2. Install the receiver service file using your actual receiver serial port:

```bash
bash ./scripts/install_service.sh receiver --serial-port /dev/ttyS0 --baudrate 9600 --host 0.0.0.0 --port 5000
```

3. Enable it to start at boot and start it now:

```bash
sudo systemctl enable --now lora-receiver
```

4. Check that it is running:

```bash
sudo systemctl status lora-receiver
```

5. Follow the logs if needed:

```bash
journalctl -u lora-receiver -f
```

### Sender Pi service

1. SSH into the sender Pi and go to the repo:

```bash
cd ~/LoRa-Ultimate-Copy
```

2. Install the sender service file using your actual sender-side serial devices:

```bash
bash ./scripts/install_service.sh sender --source-port /dev/ttyUSB0 --lora-port /dev/ttyS0 --source-baudrate 115200 --lora-baudrate 9600
```

3. Enable it to start at boot and start it now:

```bash
sudo systemctl enable --now lora-sender
```

4. Check that it is running:

```bash
sudo systemctl status lora-sender
```

5. Follow the logs if needed:

```bash
journalctl -u lora-sender -f
```

### Useful service commands

```bash
sudo systemctl restart lora-receiver
sudo systemctl restart lora-sender
sudo systemctl stop lora-receiver
sudo systemctl stop lora-sender
sudo systemctl disable lora-receiver
sudo systemctl disable lora-sender
```

## Troubleshooting

### Check whether the services are running

Receiver:

```bash
sudo systemctl status lora-receiver --no-pager
```

Sender:

```bash
sudo systemctl status lora-sender --no-pager
```

You want to see `active (running)`.

### Check whether the services will start at boot

Receiver:

```bash
sudo systemctl is-enabled lora-receiver
```

Sender:

```bash
sudo systemctl is-enabled lora-sender
```

You want to see `enabled`.

### Check the exact command each service is using

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

### Check recent logs

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

## Updating a Pi

### Manual update

If you are not using services yet, update the repo in place and then restart the Python command manually:

```bash
cd ~/LoRa-Ultimate-Copy
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
```

### One-command update

If the Pi repo was cloned with Git, you can update it with a single command:

```bash
cd ~/LoRa-Ultimate-Copy
bash ./scripts/update_lora.sh
```

What `update_lora.sh` does:

- stops if tracked repo files have local changes,
- runs `git pull --ff-only`,
- installs Python dependencies from `requirements.txt`,
- restarts `lora-sender` and/or `lora-receiver` if those services are installed.

If no service is installed yet, the script still updates the repo and dependencies, and then you can restart the Python app manually.

## Next setup improvements

Useful next steps after bench validation:

- add a packet replay or simulator script for testing without hardware,
- confirm and document the final UART settings and LoRa module configuration.
