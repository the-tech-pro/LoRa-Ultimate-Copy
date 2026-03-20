# eChook LoRa Telemetry Gateway PRD

## TL;DR
We will tap the eChook UART output using the Bluetooth module header/pads (the same 5-byte packets used for Bluetooth), feed it into the RA-08H RP2040 board, bundle packets into 1 Hz LoRa P2P frames for reliability, then receive/decode them on the Elecrow ESP32 gateway. The gateway will show connection status plus rotating stats on the LCD and host a live dashboard over WiFi AP by default, with optional WiFi STA and Ethernet support.

## Goals
- Acquire live eChook telemetry without using Bluetooth or plugging in the Bluetooth module.
- Use existing hardware: RA-08H node board + Elecrow ESP32 gateway.
- Show core telemetry and link status on the gateway LCD.
- Provide a simple live dashboard accessible via WiFi AP, WiFi STA, or Ethernet.
- Prioritize reliability at ~1 Hz updates.

## Non-goals
- Full LoRaWAN network support (use LoRa P2P).
- Multi-car support (single car for now).
- Cloud telemetry (local only).

## System Overview
Data path:
1) eChook TX (UART) -> RA-08H UART RX (5V level).
2) RA-08H RP2040 parses 5-byte eChook packets.
3) RP2040 bundles packets into a LoRa P2P frame at 1 Hz and transmits.
4) ESP32 gateway receives LoRa, decodes packets, updates LCD and dashboard.

## Hardware
- eChook board (Arduino-based). We will not plug in the HC-05 module; we only use its header/pads as a UART tap point.
- Elecrow RA-08H LoRaWAN Node Board (RP2040 + RA-08H LoRa module).
- Elecrow LoRaWAN Gateway Module (ESP32 + SX1276/RA-01H + LCD).

### Power/voltage notes (from datasheets/docs)
- eChook HC-05 module uses 5V power and is connected to Arduino TX/RX (we are not installing the module; we only use its header/pads).
- RA-08H node board powered by USB-C 5V; Crowtail UART is 5V-level.
- Gateway powered by USB-C 5V, internal 3.3V rail.

## Interfaces and Wiring
- eChook TX -> RA-08H UART RX (Crowtail UART RX) via the Bluetooth module header/pads.
- eChook GND -> RA-08H GND.
- RA-08H TX -> eChook RX is optional (only if needed for future commands).
- Bluetooth module is not installed; we use its header/pads as the UART breakout for TX/GND (and RX if needed).

## Telemetry Packet Format
### eChook 5-byte frame (UART)
Each measurement is:
```
{ id data1 data2 }
```
- Start byte: '{' (123)
- id: single ASCII char
- data1, data2: encoded value
- End byte: '}' (125)

### Value decoding rules
From eChook docs/firmware:
- If value <= 127:
  - data1 = integer part
  - data2 = 2 decimal places
  - 0xFF is used instead of 0 to avoid null bytes
- If value > 127:
  - data1 = hundreds part + 128 (MSB set to mark integer)
  - data2 = tens/units
  - 0xFF used in place of 0 if needed

### Probably Known IDs (from eChook firmware)
- s: speed (m/s)
- m: motor RPM
- i: current (A)
- v: total battery voltage (V)
- w: lower battery voltage (V)
- t: throttle input (%)
- d: throttle output (%)
- T: throttle voltage
- a: temp1 (C)
- b: temp2 (C)
- c: internal temp (C)
- r: gear ratio
- B: brake
- L: launch button
- C: cycle view button
- V: ADC reference voltage

## LoRa P2P Frame Format (proposed)
Bundle multiple 5-byte packets into one LoRa payload at 1 Hz.

Example:
```
0xEC | seq | count | [packet1..packetN]
```
- 0xEC: frame marker
- seq: rolling sequence number (0-255)
- count: number of 5-byte eChook packets
- packetN: raw 5-byte eChook frames

Optional: add a simple checksum byte at the end if needed (LoRa CRC may be enough).

## LCD Requirements (Gateway)
- Always show a simple connection status: YES/NO.
  - YES if packets seen in last N seconds (e.g., 2s).
- Rotate views every few seconds:
  - View A (core): speed, current, total voltage, temp1, temp2.
  - View B (link): RSSI, SNR, packet rate, last packet age.
  - View C (extra): RPM, throttle %, lower voltage (optional).

## Dashboard Requirements (Gateway)
- Serve a simple live dashboard with:
  - Core telemetry values.
  - Link stats (RSSI, SNR, packet rate, last packet age).
  - Connection status.
- Update rate: 1 Hz.

### Network modes (LoRa Gateway)
- WiFi AP (default): gateway hosts SSID + dashboard.
- WiFi STA (optional): gateway joins pit WiFi and serves dashboard.
- Ethernet (optional): serve dashboard over wired LAN.
- USB-C serial: debug stream only.

## Firmware Components
### RA-08H (RP2040)
- UART reader @ 115200 baud.
- eChook frame parser and value decoder.
- Buffer values; build LoRa P2P payload at 1 Hz.
- LoRa transmit with fixed frequency/SF/BW.

### Gateway (ESP32)
- LoRa receive + RSSI/SNR capture.
- Parse LoRa payload into eChook frames.
- Decode values; maintain latest state.
- LCD UI with rotating views.
- HTTP server + live updates (WebSocket or SSE).
- Network configuration for AP/STA/Ethernet.

## Reliability and Constraints
- Use 1 Hz updates for reliability.
- LoRa P2P avoids LoRaWAN overhead and fits single-car use.
- EU868 duty-cycle limits apply; 1 Hz with bundled packets is safe.

## Greenpower Compliance (F24 2025/2026)
- T14.1 prohibits transmitting any electronic data to the car/driver; only verbal/visual communication to the driver is allowed.
- T14.2 requires telemetry/communications to operate at national legal frequencies and power levels.
- Design decision: car node is TX-only (no downlink, no acknowledgements, no commands to car).
- Gateway must not transmit to the car during events.
- Source PDFs:
  - 2025 F24 regs: https://www.greenpower.co.uk/sites/default/files/uploads/2025/Regulations/F24%20Technical%20and%20Sporting%20Regulations%202025%20v1.0.pdf
  - 2026 F24 regs: https://www.greenpower.co.uk/sites/default/files/uploads/2026/Technical/F24%20Technical%20and%20Sporting%20Regulations%202026%20v1.0.pdf

## Implementation Strategy (phased)
1) Validate eChook UART output:
   - Confirm 115200 baud and 5-byte frames on a serial reader.
2) RA-08H UART parsing:
   - Parse and decode eChook frames, log to USB serial.
3) LoRa P2P link:
   - Transmit bundled payload from RA-08H, receive on gateway.
4) Gateway decode + LCD:
   - Decode frames, show connection status + rotating stats.
5) Dashboard:
   - Serve live data over WiFi AP, add STA/Ethernet options.

## Current Status (as of latest changes)
- Phase 1 is validated: eChook UART output is confirmed on the HC-05 header pads.
- Note: the header silk labels are from the HC-05 module's perspective. The pad labeled `RXD` carries eChook TX data (connect your USB-UART RX there).
- A small local viewer tool exists:
  - `uart_read.ps1` provides a simple GUI to view decoded eChook values (1 row per ID).
  - `uart_read_gui.cmd` is a clickable launcher (defaults to COM5 @ 115200).
  - The GUI shows connected/disconnected state and lets you pick a COM port.

## Developer Onboarding (new coders)
- Start here: read this PRD in full, then review `eChookCode/eChook_Functions.ino` to see the 5-byte frame format and `sendData(...)` usage.
- Confirm your board/serial wiring using the Phase 1 notes above before moving to LoRa work.
- Keep changes aligned to the Goals/Non-goals and the greenpower compliance notes.

## Testing and Validation
- Bench test UART decoding using known eChook output.
- Range test at 1 Hz with RSSI/SNR logging.
- LCD display verification for all fields.
- Dashboard responsiveness check on phone and laptop.

## Open Questions
- Confirm eChook header pinout for TX/GND access.
- Confirm exact LoRa frequency/SF/BW for the race environment.
- Decide if checksum is needed in LoRa payload.
- Confirm LCD UI library choice for the gateway firmware.
