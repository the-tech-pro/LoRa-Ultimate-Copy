# eChook LoRa Telemetry Dashboard PRD

## TL;DR
This project replaces the existing eChook Bluetooth link with a LoRa link while keeping the eChook telemetry packet format unchanged. The default system is:

```text
eChook -> UART -> USB-to-UART adapter -> USB -> Sender Pi -> UART -> LoRa -> air -> LoRa -> Receiver Pi -> Flask dashboard
```

The simpler fallback system is:

```text
eChook -> UART -> LoRa -> air -> LoRa -> Receiver Pi -> Flask dashboard
```

The receiver Raspberry Pi is responsible for parsing packets, decoding values, adding timestamps, and serving a live local dashboard.

## Product Goal
Build a lightweight, reliable local telemetry system that:
- reuses the eChook's existing UART/Bluetooth data output,
- sends it over LoRa instead of Bluetooth,
- displays live vehicle telemetry on a receiver-side dashboard,
- stays simple for the first working version and leaves room for later expansion.

## Core Principle
The main design principle is simple:

> Replace Bluetooth with LoRa and keep the rest of the telemetry flow as close to the existing eChook output as possible.

## In Scope
- Reading raw eChook UART telemetry packets.
- Sending telemetry over a LoRa serial link.
- Receiving telemetry on a Raspberry Pi.
- Decoding raw packets into usable values.
- Adding timestamps on the receiver side.
- Displaying live telemetry in a Flask dashboard.
- Showing at least speed, voltage, current, and temperatures in the dashboard.

## Out of Scope
- Changing the eChook packet format.
- Sending commands back to the car.
- Cloud sync or internet-facing telemetry.
- Multi-car support.
- Historical analytics or complex long-term storage in the first version.
- A native mobile app.

## System Overview
### Default architecture: Sender Pi in the car
```text
eChook -> UART -> USB-to-UART adapter -> USB -> Sender Raspberry Pi -> UART -> LoRa radio -> air ->
LoRa radio -> Receiver Raspberry Pi -> Flask dashboard
```

This is the recommended architecture because the sender Pi can:
- validate incoming packets,
- buffer or batch packets if needed,
- add GPS or other sensors later,
- improve reliability without changing the eChook side.

### Simpler architecture: direct eChook to LoRa
```text
eChook -> UART -> LoRa radio -> air -> LoRa radio -> Receiver Raspberry Pi -> Flask dashboard
```

This is acceptable as a simpler fallback, but it is not the default delivery target because it removes the flexibility and observability provided by the sender Pi.

## Key Design Decisions
- Reuse the eChook's existing UART/Bluetooth packet format instead of creating a new telemetry protocol.
- Treat the LoRa link as the wireless replacement for Bluetooth.
- Use the sender Pi architecture as the default because it gives better control, debugging, and future extensibility.
- Add timestamps on the receiver because the source packets do not include time data.
- Keep the first release simple, then add batching, logging, GPS, or extra sensors later if needed.

## Primary Hardware
- eChook controller with UART telemetry output using the same format as its Bluetooth output.
- Sender side:
  - Default: Raspberry Pi plus LoRa module connected over UART.
  - Current bench setup: the eChook UART is brought into the sender Pi using a USB-to-UART adapter plugged into the sender Pi over USB.
  - Optional simplified build: LoRa module directly connected to the eChook UART.
- Receiver side:
  - Raspberry Pi running the receiver and dashboard.
  - LoRa module connected to the Pi over UART.

## Software Stack
- Raspberry Pi OS Lite
- Python 3
- `pyserial` for UART communication
- `flask` for the local dashboard

## Telemetry Source: eChook UART / Bluetooth Output
The eChook already emits compact telemetry over UART using the same protocol used by its Bluetooth module.

Each telemetry packet is exactly 5 bytes:

```text
[{][id][data1][data2][}]
```

Where:
- `{` is the start byte
- `id` is a single-character sensor identifier
- `data1` and `data2` carry the value
- `}` is the end byte

The bytes are raw serial bytes, not a human-readable text payload.

## Packet Decoding Rules
The receiver must decode values exactly according to the eChook encoding scheme.

### Framing
- A valid packet starts with byte `123` (`{`).
- A valid packet ends with byte `125` (`}`).
- Packet length is always 5 bytes.

### Zero value
- A sensor value of zero is encoded as:
  - `data1 = 0xFF`
  - `data2 = 0xFF`

### Values up to 127
If the original value is less than or equal to `127`, the value is encoded with up to two decimal places:

```text
value = integer_part + decimal_part / 100
```

Rules:
- `data1` carries the integer part
- `data2` carries the decimal part
- `0xFF` is used in place of `0` for either component

Examples:
- `12.34` -> `data1 = 12`, `data2 = 34`
- `12.00` -> `data1 = 12`, `data2 = 0xFF`
- `0.56` -> `data1 = 0xFF`, `data2 = 56`
- `0.00` -> `data1 = 0xFF`, `data2 = 0xFF`

### Values above 127
If the original value is greater than `127`, it is encoded as an integer:

```text
value = (hundreds_part * 100) + tens_units_part
```

Rules:
- `data1` stores the hundreds/thousands portion with `128` added to mark integer mode
- `data2` stores the tens/units portion
- `0xFF` is used in place of `0` where needed

Decode rule:

```text
value = ((data1 - 128) * 100) + normalized(data2)
```

Where `normalized(x)` means treat `0xFF` as `0`.

### Receiver decoding logic
The receiver-side decoder must follow this order:
1. Verify framing bytes.
2. If `data1 == 0xFF` and `data2 == 0xFF`, decode the value as `0`.
3. Else if `data1 >= 128` and `data1 != 0xFF`, decode as an integer value above `127`.
4. Else decode as a value up to `127` using `integer + decimals / 100`.

## Confirmed Telemetry Identifier Table
The following raw packet identifiers are confirmed from the eChook Arduino Nano code in `globals.h`.

| ID | Constant | Meaning | Units / Notes |
| --- | --- | --- | --- |
| `s` | `SPEED_ID` | Speed | m/s |
| `m` | `MOTOR_ID` | Motor speed | RPM |
| `i` | `CURRENT_ID` | Current | A |
| `v` | `VOLTAGE_ID` | Total battery voltage | V |
| `w` | `VOLTAGE_LOWER_ID` | Lower battery voltage | V |
| `t` | `THROTTLE_INPUT_ID` | Throttle input | % |
| `d` | `THROTTLE_OUTPUT_ID` | Throttle output | % |
| `T` | `THROTTLE_VOLTAGE_ID` | Throttle input voltage | V |
| `a` | `TEMP1_ID` | Temperature 1 | C |
| `b` | `TEMP2_ID` | Temperature 2 | C |
| `c` | `TEMP3_ID` | Internal temperature | C |
| `L` | `LAUNCH_MODE_ID` | Launch mode / start button | button state |
| `C` | `CYCLE_VIEW_ID` | Cycle view / screen button | button state |
| `r` | `GEAR_RATIO_ID` | Calculated gear ratio | ratio |
| `B` | `BRAKE_PRESSED_ID` | Brake pressed | on/off |
| `V` | `REF_VOLTAGE_ID` | ADC reference voltage | V |

### Derived values
Not every dashboard field necessarily comes from a dedicated raw eChook packet identifier.

Examples:
- packet age and receive time are added on the receiver Pi,
- connection status is derived from recent packet activity,
- any future computed metrics such as charts, summaries, or derived battery values should be treated as receiver-side calculations unless a raw eChook identifier exists for them.

## Sender Requirements
### Default sender mode: Raspberry Pi bridge
The sender Pi must:
- read raw 5-byte packets from the eChook UART,
- validate framing before forwarding,
- forward telemetry to the LoRa module over UART,
- avoid changing the meaning of the original eChook packets,
- keep the implementation simple in the first version.

For the current bench setup, the eChook UART reaches the sender Pi through a USB-to-UART adapter, so the sender Pi reads the eChook telemetry from a USB serial device.

The sender Pi may also:
- batch multiple eChook packets into a LoRa transmission,
- tag packets with sender-side metadata in a future version,
- merge in GPS or other sensors later.

### Simplified sender mode: direct eChook to LoRa
If the direct wiring approach is used:
- the LoRa radio acts as a transparent serial bridge,
- the receiver-side decode path stays the same,
- sender-side preprocessing is not available.

This option is supported conceptually, but the initial implementation target remains the sender Pi architecture.

## Receiver Requirements
The receiver Raspberry Pi must:
- read telemetry bytes from the LoRa UART,
- reconstruct 5-byte eChook packets,
- validate framing,
- decode values from `id`, `data1`, and `data2`,
- add a receive timestamp because eChook packets do not contain one,
- store the latest value per telemetry identifier,
- make the latest decoded state available to the Flask dashboard.

The receiver timestamp is the authoritative timestamp for the first version of the system.

## Dashboard Requirements
The dashboard runs on the receiver Pi and must be implemented in Flask.

### Dashboard must show
- connection status
- latest update time / packet age
- speed
- voltage
- current
- temperatures

### Dashboard behavior
- Refresh automatically roughly once per second.
- Prefer a simple local-web implementation over a complex frontend stack.
- Be usable on a laptop or phone connected to the receiver Pi's local network.

### Initial data model
The first version only needs to maintain the latest known value for each telemetry field plus its receive timestamp.

Persistent history is not required for the first version.

## Networking and Deployment
- The dashboard is hosted locally on the receiver Raspberry Pi.
- The system is intended to work on a local network without cloud services.
- Receiver services should be suitable for running headless on Raspberry Pi OS Lite.

## Functional Requirements
1. The system must accept the raw 5-byte eChook UART packet format without redesigning the payload structure.
2. The default architecture must support a sender Raspberry Pi between the eChook and LoRa radio.
3. The system must also remain compatible with a future direct eChook-to-LoRa build.
4. The receiver must add timestamps because the source packets do not include time data.
5. The receiver must decode values consistently with the published eChook Bluetooth/UART encoding rules.
6. The dashboard must present live telemetry with approximately 1 second refresh behavior.
7. The first release must prioritize simplicity and reliability over advanced features.

## Non-Functional Requirements
- Keep the first implementation lightweight and easy to debug.
- Preserve the original eChook packet semantics end to end.
- Minimize custom protocol complexity over the LoRa link in the first version.
- Make it easy to extend later with batching, GPS, extra sensors, or data logging.

## Assumptions
- The eChook UART output used here is the same data stream and packet format as the Bluetooth module output.
- The current sender-side bench setup uses a USB-to-UART adapter to bring the eChook UART into the sender Pi over USB.
- The current bench setup uses `115200` baud for the UART links.
- The exact UART settings used in the current bench setup should be revalidated during implementation.
- A small amount of receiver-side latency is acceptable as long as the dashboard feels live.

## Delivery Phases
### Phase 1: Receiver-side proof of life
- Read LoRa UART on the receiver Pi.
- Parse raw 5-byte packets.
- Decode values correctly.
- Show them in a minimal Flask dashboard.

### Phase 2: Sender Pi bridge
- Read eChook UART on a sender Pi.
- Forward packets over LoRa.
- Confirm end-to-end telemetry flow.

### Phase 3: Hardening
- Improve packet validation and error handling.
- Add optional batching if it improves radio performance.
- Add service startup and deployment polish.

### Phase 4: Extensions
- Add GPS or additional sender-side sensors.
- Add optional logging or historical charts.
- Add more advanced dashboard views if needed.

## Success Criteria
- Live eChook telemetry reaches the receiver Pi over LoRa.
- The receiver decodes incoming packets into correct engineering values.
- The dashboard updates automatically and shows useful live telemetry.
- The implementation works with the existing eChook telemetry format rather than inventing a new one.

## Open Questions
- Revalidate that `115200` is the correct UART setting for the final sender-side deployment.
- Confirm the exact LoRa hardware pair and any constraints they impose on transparent UART forwarding.
- Decide whether batching is needed for the initial deployment or can wait until after the first end-to-end demo.
