---
type: concept
title: X-Mount Electronic Lens Protocol & Snap Focus
description: Reverse-engineered Fujifilm X-mount electronic lens SPI protocol, packet framing, motor stepping commands, and standalone ARMv7-A Snap Focus payload.
tags: [lens, x-mount, snap-focus, spi, motor, autofocus]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-28T21:29:05.191Z
sources:
  - id: openwiki-source-24b4048fab464560b1dd0501
    resource: repo://docs/X_MOUNT_LENS_PROTOCOL.md
  - id: openwiki-source-c6b4b1993f58de090c24ca8c
    resource: repo://payloads/snap_focus/snap_focus.c
generated: { by: "omp", at: "2026-10-28T21:29:05.191Z" }
---

# X-Mount Electronic Lens Protocol & Snap Focus

Fujifilm X-mount lenses contain internal microcontrollers that communicate with the camera body over electronic bayonet spring pins using a synchronous SPI-like protocol. Controlling focus motor steps directly allows implementing instant zone-focusing / snap focus (similar to the Ricoh GR) on cameras like the Fujifilm X-T10.

## Physical Interface & Protocol Framing

The communication between the EXR Processor II and the lens MCU operates as a synchronous serial link:
- **Clock:** ~1 MHz SCLK, mode 0 (CPOL=0, CPHA=0), MSB-first.
- **Packet Structure:** Fixed 8-byte command/response frames.

| Byte Offset | Field | Value / Format | Purpose |
|---|---|---|---|
| `0` | `SYNC` | `0xA5` | Start-of-frame synchronization byte |
| `1` | `CMD` | `uint8` | Lens command opcode |
| `2 - 3` | `ARG0` | `uint16_le` | Primary command argument (e.g. target position) |
| `4 - 5` | `ARG1` | `uint16_le` | Secondary argument |
| `6` | `CHECKSUM` | `uint8` | XOR parity of bytes 1 through 5 |
| `7` | `END` | `0x5A` | End-of-frame termination marker |

## Initialization & Command Codes

The lens initialization handshake occurs at physical offset `0x0056f000 - 0x0056f400` in the X-T10 firmware (identifiable by the ASCII string `START_NEGO` at `0x0056f172`):

1. **`CMD_START_NEGO` (`0x00`):** Initiates communication handshake and requests lens metadata.
2. **`CMD_LENS_STATUS` (`0x01`):** Polls status register until the lens reports `READY`.
3. **`CMD_LENS_MOVE_STEP` (`0x12`):** Directs the focus motor to move relative signed steps.
4. **`LENS_GET_POSITION` (`0x21`):** Returns the current optical element encoder position.
5. **`LENS_SET_POSITION` (`0x23`):** Moves the focus motor directly to an absolute step index.
6. **`CMD_APERTURE_SET` (`0x30`):** Commands the electronic aperture diaphragm blades.

## Snap Focus Implementation

In standard firmware, manual focus relies on continuous electronic fly-by-wire ring encoder ticks, which slows down street photography focus acquisition.

The `payloads/snap_focus/` payload implements an instant zone-focusing routine:
- Intercepts user inputs (e.g. Fn button or AF-L press in Manual Focus mode).
- Bypasses contrast/phase detection autofocus loops.
- Employs calibrated absolute motor positions:
  - **1.0 m:** ~1420 steps (close portraits).
  - **1.5 m:** ~980 steps.
  - **2.0 m:** ~740 steps (street hyperfocal baseline for 18mm/27mm lenses).
  - **5.0 m:** ~310 steps.
  - **Infinity ($\infty$):** 0 steps.
- Compiles into an independent, position-independent ARMv7-A payload (`snap_focus.bin`).

## Dynamic Auto ISO (Focal-Length-Aware Shutter Speed)

Modern Fujifilm bodies use current focal length reported by the lens MCU (`CMD_LENS_INFO` `0x40`) to dynamically calculate minimum shutter speed:
$$T_{\text{min}} = \frac{1}{\text{Crop Factor} \times f \times 2^{\text{Shift}}}$$

The `core/auto_iso.py` module models this modern 3-slot Auto ISO engine (AUTO 1, AUTO 2, AUTO 3):
- **Shift Modes:** Slower (-2 EV), Slow (-1 EV), Standard (0 EV), Fast (+1 EV), Faster (+2 EV).
- **Quantization:** Rounds to exact photographic shutter speed stops (e.g. 1/60s, 1/125s, 1/250s) matching physical camera exposure steps.
