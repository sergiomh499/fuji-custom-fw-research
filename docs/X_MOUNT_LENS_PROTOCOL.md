# Fujifilm X-Mount Electronic Lens Communication Protocol

Reverse-engineering notes for the X-T10 (EXR Processor II) lens interface.
All offsets are physical file offsets in the unpacked `xt10_v131.bin`
(53,084,624 bytes) unless noted.

## 1. Transport

- **Physical layer:** SPI-like synchronous serial between the EXR Processor II
  (master) and the lens MCU (slave). A separate low-speed UART is used for
  debug/telemetry only.
- **Clock:** ~1 MHz SCLK, MSB-first, mode 0 (CPOL=0, CPHA=0).
- **Chip select:** active low, one transaction per command.
- **Word size:** 32-bit little-endian frames.

## 2. Packet Framing

Every lens transaction is a fixed 8-byte frame:

| Offset | Size | Field        | Description                              |
|--------|------|--------------|------------------------------------------|
| 0      | 1    | `SYNC`       | `0xA5` start-of-frame marker             |
| 1      | 1    | `CMD`        | Command code (see section 4)             |
| 2      | 2    | `ARG0`       | Primary argument (little-endian)         |
| 4      | 2    | `ARG1`       | Secondary argument (little-endian)       |
| 6      | 1    | `CHECKSUM`   | XOR of bytes 1..5                        |
| 7      | 1    | `END`        | `0x5A` end-of-frame marker               |

The master waits for the lens to raise `STATUS_READY` (bit 0 of the status
register) before issuing the next frame.

## 3. Initialization Negotiation

Located at `0x0056f000 - 0x0056f400` (string `START_NEGO` at `0x0056f172`).

Sequence:

1. Master asserts power (`SYS_LENS_POW`).
2. Master sends `START_NEGO` command (`CMD = 0x00`).
3. Lens replies with vendor/id block (`"LENS"`, firmware version).
4. Master sends `LENS_STATUS` poll until `READY`.
5. Master sends `LENS_SET_POSITION` with the stored infinity position to
   calibrate the focus motor.

## 4. Command Codes

| Name                  | Code | Direction | Description                              |
|-----------------------|------|-----------|------------------------------------------|
| `CMD_START_NEGO`      | 0x00 | M->L      | Begin negotiation                        |
| `CMD_LENS_STATUS`     | 0x01 | M->L      | Read lens status / ready bit             |
| `CMD_LENS_MOVE_STEP`  | 0x12 | M->L      | Move focus motor by signed step count    |
| `LENS_GET_POSITION`   | 0x21 | M->L      | Read current focus motor position        |
| `LENS_SET_POSITION`   | 0x23 | M->L      | Set absolute focus motor position        |
| `CMD_LENS_IRIS`       | 0x30 | M->L      | Set aperture (iris) value                |
| `CMD_LENS_INFO`       | 0x40 | M->L      | Read lens identity / focal length        |

## 5. Focus Motor Position

- Position is a signed 32-bit step count relative to the infinity hard stop.
- `LENS_GET_POSITION` returns the current step count.
- `LENS_SET_POSITION` moves the motor to an absolute step count.
- `CMD_LENS_MOVE_STEP` adds a signed delta to the current position.

## 6. Focus Distance Scale

The firmware exposes a human-readable distance via the `DISTANCE: %n` format
string. Snap Focus maps a target distance to a motor step count:

| Preset     | Distance (mm) | Motor steps (approx.) |
|------------|---------------|-----------------------|
| Near       | 1500          | 667                   |
| Mid        | 2000          | 500                   |
| Far        | 5000          | 200                   |
| Infinity   | 0             | 0x7fffffff (sentinel) |

Steps are derived as `steps = 1000000 / distance_mm` (monotonic, calibrated
per lens).

## 7. Snap Focus Payload

`payloads/snap_focus/snap_focus.c` implements a position-independent ARMv7-A
payload that:

1. Hooks the AF-L / Fn button handler (or Command Dial click in MF mode).
2. Cycles through the presets in section 6.
3. Transmits `CMD_LENS_MOVE_STEP` followed by `LENS_SET_POSITION` over the
   lens MMIO registers at `0x40021000`.

Build:

```
cd payloads/snap_focus && make
```

Produces `snap_focus.bin` (position-independent, < 1 KiB).

## 8. Fujihack Hook Points

- `FIRM_TAKEPIC` at `0x0096cc80`: capture entry point, safe place to chain.
- Key handlers in the `0x0056f000` region dispatch button events including
  `ONEPUSH_A` and `snapmf(%d)`.

## 9. Safety

- Always keep a backup of the original firmware.
- Snap Focus only issues lens commands; it does not modify sensor or storage.
- Test on a tripod with the lens cap off; unexpected motor movement can
  stress the focus mechanism.
