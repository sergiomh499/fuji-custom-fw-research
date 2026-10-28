---
type: concept
title: Hardware Safety, Telemetry & Debricking Runbook
description: Three-tier brick risk taxonomy, failure mitigations, physical UART serial debugging pinouts, and in-circuit SPI flashrom recovery procedures.
tags: [hardware, safety, debricking, uart, flashrom, spi]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-28T21:29:05.191Z
sources:
  - id: openwiki-source-edf16bf565a5bb29a4da773b
    resource: repo://docs/BRICK_ANALYSIS_AND_RECOVERY.md
  - id: openwiki-source-14310859817466c3f158dc9a
    resource: repo://docs/HARDWARE_TELEMETRY_AND_RECOVERY.md
generated: { by: "omp", at: "2026-10-28T21:29:05.191Z" }
---

# Hardware Safety, Telemetry & Debricking Runbook

Modifying embedded firmware introduces distinct risks ranging from benign software assertion loops to complete non-volatile memory corruption. This guide details the mitigation taxonomy, hardware debugging test points, and SPI debricking procedures.

## Three-Tier Brick Risk Taxonomy

| Tier | Failure Mechanism | Risk Level | Recovery Mechanism |
|---|---|---|---|
| **Level 1 (Soft Brick)** | Payload crash in user space / menu callback; corrupt volatile RAM state | Minimal | Battery pull; factory bootloader reloads uncorrupted flash on next boot. |
| **Level 2 (Semi-Brick)** | Corrupted application code in flash; infinite RTOS panic loop before UI load | Medium | Force factory bootloader by holding `DISP/BACK` on power-on with stock firmware on SD card. |
| **Level 3 (Hard Brick)** | Interrupted flash write; corrupted bootloader partition (first 64 KB of SPI flash) | Critical | Hardware SPI flasher (CH341A / Raspberry Pi) with Pomona 5250 clip and `flashrom`. |

## Hardware UART Telemetry

Both the Fujifilm X-T10 and FinePix X10 expose diagnostic UART console lines on physical test pads near the central processor:

- **Logic Level:** 3.3V LVCMOS (non-5V tolerant).
- **Serial Framing:** 115200 bps, 8 data bits, no parity, 1 stop bit (115200 8N1).
- **Test Pads:**
  - `TP_TX`: Camera debug output.
  - `TP_RX`: Command input (pull-up).
  - `GND`: Common ground.

Connecting an isolated 3.3V USB-UART adapter (such as FTDI FT232RL or Raspberry Pi Pico) allows real-time monitoring of RTOS kernel logs, KASAGO network assertions, and boot errors.

## In-Circuit SPI Flash Debricking (Level 3 Recovery)

When the primary bootloader partition is corrupted and the camera does not respond to `DISP/BACK`, in-circuit SPI flashing restores the firmware:

1. **Target Flash Chip:** SOIC-8 SPI NOR Flash (Winbond W25Q128 / Macronix MX25L128, 16 MB).
2. **Attachment:** Seat a Pomona 5250 SOIC-8 test clip over the flash package while the camera battery is removed.
3. **Hardware Programmer:** CH341A USB programmer set to 3.3V mode.
4. **Read & Verification:**
   ```bash
   flashrom -p ch341a_spi -c "W25Q128.V" -r dump_a.bin
   flashrom -p ch341a_spi -c "W25Q128.V" -r dump_b.bin
   cmp dump_a.bin dump_b.bin
   ```
5. **Flash Recovery:**
   ```bash
   flashrom -p ch341a_spi -c "W25Q128.V" -w clean_stock_firmware.bin
   ```

## Cold-Hooking Safety Principle

To prevent Level 2 and Level 3 bricks during custom code execution, new functions MUST NOT be hooked into early boot or sensor initialization routines. Instead, payloads are injected into user-invoked secondary menus (such as Instax Share or Voice Memo). If a cold-hooked payload encounters an unhandled exception, power cycling the camera immediately restores stock operation.
