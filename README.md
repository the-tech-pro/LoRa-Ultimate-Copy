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
git clone <your-repo-url>
cd "LoRa Ultimate Copy"
```

### 3. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Receiver Pi setup and run

### Wiring

Connect the receiver-side LoRa module UART to the receiver Raspberry Pi UART or USB serial adapter.

You will need the correct Linux serial device, for example:

- `/dev/ttyUSB0`
- `/dev/ttyAMA0`
- `/dev/serial0`

### Run the receiver app

```bash
source .venv/bin/activate
python3 receiver_app.py --serial-port /dev/ttyUSB0 --baudrate 9600 --host 0.0.0.0 --port 5000
```

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
- the LoRa module is the second serial link used by the sender Pi.

Expected signal flow:

```text
eChook UART -> USB-to-UART adapter -> USB -> Sender Pi serial input
Sender Pi UART output -> LoRa module UART input
```

Use the actual serial device names for your sender Pi and attached radio.

Examples:

- eChook side via USB-to-UART adapter: `/dev/ttyUSB0`
- LoRa side: `/dev/ttyAMA0`, `/dev/serial0`, or another USB serial device depending on your wiring

### Run the sender bridge

```bash
source .venv/bin/activate
python3 sender_bridge_app.py --source-port /dev/ttyUSB0 --lora-port /dev/serial0 --source-baudrate 9600 --lora-baudrate 9600
```

The sender bridge does not decode or transform packets. It validates framing and forwards valid 5-byte packets unchanged, which matches the PRD requirement to preserve the original eChook packet semantics.

## UART and LoRa notes

- The current code defaults to `9600` baud because the PRD leaves final UART settings as an open question.
- Revalidate the real eChook UART settings on the bench before final deployment.
- The LoRa pair should be configured so the radios act as a transparent serial link for this first version.
- This first version does not add a custom protocol, batching, or sender-side metadata.

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

## Next setup improvements

Useful next steps after bench validation:

- add `systemd` service files for both Pis,
- add a packet replay or simulator script for testing without hardware,
- confirm and document the final UART settings and LoRa module configuration.
