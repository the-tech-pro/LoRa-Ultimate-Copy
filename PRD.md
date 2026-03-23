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
- allows the operator to start and stop named telemetry recordings,
- supports later playback of those recordings through the same dashboard,
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
- User-controlled recording sessions stored on the receiver Pi.
- Naming recordings and marking laps during an active recording.
- Playing back saved recordings through a dashboard view that mirrors the live dashboard.
- Showing storage usage and recording management controls in the dashboard.

## Out of Scope
- Changing the eChook packet format.
- Sending commands back to the car.
- Cloud sync or internet-facing telemetry.
- Multi-car support.
- Always-on background logging when no recording has been started.
- Complex long-term analytics in the first version.
- Automatic lap detection.
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
- Keep the live dashboard and the recording playback dashboard visually aligned so operators do not need to learn two separate interfaces.
- Persist telemetry only when the user explicitly starts a recording.
- Store recordings on the receiver Pi using lightweight append-only raw packet logs plus authoritative receiver timestamps.
- Keep storage management local to the receiver Pi dashboard with explicit visibility into used and available space.
- Keep the implementation simple, then add batching, GPS, or extra sensors later if needed.

## Primary Hardware
- eChook controller with UART telemetry output using the same format as its Bluetooth output.
- Sender side:
  - Default: Raspberry Pi plus LoRa module connected over UART.
  - Current bench setup: the eChook UART is brought into the sender Pi using a USB-to-UART adapter plugged into the sender Pi over USB.
  - Current bench setup: the sender-side SX1268 LoRa HAT is mounted on the Raspberry Pi GPIO header and controlled through the Pi UART, not through the HAT USB port.
  - Optional simplified build: LoRa module directly connected to the eChook UART.
- Receiver side:
  - Raspberry Pi running the receiver and dashboard.
  - LoRa module connected to the Pi over UART.
  - Current bench setup: the receiver-side SX1268 LoRa HAT is mounted on the Raspberry Pi GPIO header and controlled through the Pi UART, not through the HAT USB port.

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
For the current bench setup, the sender-side LoRa link itself is still the Raspberry Pi UART connected to the SX1268 HAT on the GPIO header.

The sender Pi may also:
- batch multiple eChook packets into a LoRa transmission,
- coalesce repeated source packets down to the latest packet per telemetry identifier if that is needed to stay within the practical LoRa link capacity,
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
- write persistent recording data only while a recording session is active,
- store validated raw packets together with the authoritative receiver timestamp,
- keep incomplete trailing data recoverable after an unexpected stop or power loss.

For the current bench setup, the receiver-side UART comes from the SX1268 HAT mounted on the Raspberry Pi GPIO header.

The receiver timestamp is the authoritative timestamp for the first version of the system.

## Recording Requirements
- Recording is off by default.
- A recording starts only when the user explicitly starts it from the live dashboard.
- A recording stops only when the user explicitly stops it, or when the receiver process exits unexpectedly.
- Each recording must have:
  - a unique recording identifier,
  - a user-visible name,
  - a start time,
  - an end time once closed,
  - packet count and size metadata,
  - a list of lap markers.
- The dashboard must allow the user to:
  - start a recording,
  - stop a recording,
  - rename a recording,
  - add lap markers during an active recording,
  - download a recording,
  - delete a recording.
- Recordings must be stored on the receiver Pi only.
- The persisted recording format should stay lightweight and should prioritize storing authoritative timestamps plus raw validated packets rather than duplicating large decoded datasets.
- Continuous always-on persistence outside an active recording is not required.

## Dashboard Requirements
The dashboard runs on the receiver Pi and must be implemented in Flask.

### Dashboard information architecture
- The dashboard must provide these top-level tabs:
  - `Live`
  - `Recordings`
  - `Storage`
  - `Settings`

### Live tab must show
- connection status
- latest update time / packet age
- speed
- voltage
- current
- temperatures
- whether a recording is active
- the active recording name if recording is active
- the active recording elapsed time if recording is active
- a clear `Start Recording` action when idle
- clear `Stop Recording` and `Lap` actions while recording

### Recordings tab must show
- a list of saved recordings with name, date, duration, lap count, packet count, and size
- actions to rename, download, and delete recordings
- a way to open a dedicated playback page for an individual recording

### Recording playback page requirements
- Opening a recording must take the user to a page that feels like the live dashboard, but driven by recorded data instead of live telemetry.
- The playback page must reuse the same key stats, graph area, and telemetry table concepts as the live dashboard.
- The playback page must support:
  - play,
  - pause,
  - jump to start,
  - jump to end,
  - a scrub/timeline control,
  - playback speed control,
  - lap markers on the playback timeline.

### Storage tab must show
- total receiver storage
- currently available receiver storage
- total recording storage used
- recording quota or reserved-space settings
- cleanup and deletion controls for recordings
- clear warnings when storage is too low to safely start a new recording

### Settings tab must show
- recording-related defaults such as naming behavior
- storage-management settings such as quota and reserved free space
- any playback defaults that should persist across page loads

### Dashboard behavior
- Refresh automatically roughly once per second.
- Prefer a simple local-web implementation over a complex frontend stack.
- Be usable on a laptop or phone connected to the receiver Pi's local network.
- The `Live` tab must always reflect current receiver telemetry rather than playback data.
- The dashboard must make recording state obvious at a glance.
- The dashboard must prevent starting a recording if storage conditions are unsafe.

### Data model
- Live state must maintain the latest known value for each telemetry field plus its receive timestamp.
- Persistent history must exist only for explicit user-started recordings.
- Recording playback may derive decoded views from stored raw packet records instead of storing a second fully decoded history copy.

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
7. The dashboard must provide `Live`, `Recordings`, `Storage`, and `Settings` tabs.
8. The system must not persist telemetry unless the user has started a recording.
9. An active recording must be startable and stoppable from the `Live` tab.
10. The `Live` tab must clearly indicate when recording is active.
11. The system must allow recordings to be named and later renamed.
12. The system must allow lap markers to be added during an active recording.
13. Saved recordings must be viewable through a playback page that mirrors the live dashboard layout.
14. The system must allow recordings to be downloaded and deleted from the dashboard.
15. The dashboard must expose recording-related storage usage and management controls.
16. The implementation must prioritize simplicity and reliability over unnecessary protocol or storage complexity.

## Non-Functional Requirements
- Keep the first implementation lightweight and easy to debug.
- Preserve the original eChook packet semantics end to end.
- Minimize custom protocol complexity over the LoRa link in the first version.
- Keep recording storage efficient enough for Raspberry Pi systems with limited local storage.
- Prefer append-only and crash-tolerant recording writes over heavier storage schemes.
- Make it easy to extend later with batching, GPS, extra sensors, richer analytics, or alternate export formats.

## Assumptions
- The eChook UART output used here is the same data stream and packet format as the Bluetooth module output.
- The current sender-side bench setup uses a USB-to-UART adapter only to bring the eChook UART into the sender Pi over USB.
- The current sender-side and receiver-side SX1268 LoRa HATs are controlled through the Raspberry Pi GPIO/UART connection rather than the HAT USB port.
- In the current bench setup, the SX1268 HAT UART appears on the Pi as `/dev/ttyS0`.
- The eChook-side UART in the current bench setup is expected to use `115200` baud.
- The current working bench setup uses `9600` baud on the sender-side and receiver-side SX1268 HAT UART links.
- The exact UART settings should still be revalidated if the LoRa module configuration is changed later.
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

### Phase 3: Dashboard structure
- Introduce the `Live`, `Recordings`, `Storage`, and `Settings` tab layout.
- Keep the `Live` tab focused on current telemetry only.
- Add clear recording controls and recording-state indicators to the `Live` tab.

### Phase 4: Recording and playback
- Add receiver-side named recordings that store raw packets plus authoritative receiver timestamps.
- Add lap markers during active recordings.
- Add a recordings list and a playback page that mirrors the live dashboard experience.
- Add raw and decoded export paths for saved recordings.

### Phase 5: Storage management and hardening
- Add storage usage, quota, and cleanup controls.
- Improve packet validation, crash recovery, and recording-file integrity handling.
- Add optional batching if it improves radio performance.
- Add service startup and deployment polish.

### Phase 6: Extensions
- Add GPS or additional sender-side sensors.
- Add more advanced dashboard views if needed.
- Add richer analytics if later required.

## Success Criteria
- Live eChook telemetry reaches the receiver Pi over LoRa.
- The receiver decodes incoming packets into correct engineering values.
- The dashboard updates automatically and shows useful live telemetry.
- The operator can start and stop recordings from the live dashboard without interrupting live telemetry.
- Saved recordings can be named, reviewed through dashboard playback, downloaded, and deleted.
- Storage usage is visible and manageable from the dashboard.
- The implementation works with the existing eChook telemetry format rather than inventing a new one.

## Open Questions
- Revalidate that `115200` is the correct UART setting for the final sender-side deployment.
- Confirm whether the SX1268 pair will stay on `9600` UART permanently or be intentionally reconfigured later.
- Decide whether batching is needed for the initial deployment or can wait until after the first end-to-end demo.
- Decide the default recording quota and reserved free-space threshold for a 16 GB Raspberry Pi setup.
- Decide whether recording playback should decode fully on demand or cache an intermediate playback index.
