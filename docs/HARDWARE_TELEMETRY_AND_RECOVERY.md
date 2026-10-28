# Hardware Telemetry & Level 3 Recovery Guide

Companion reference for **Fujifilm X-T10** and **FinePix X10** custom-firmware work. Covers physical UART/SPI access and the mitigations to apply when a failure occurs at the hardware level.

**Failure mitigation cross-references:**
- Volatile / PTP RAM: [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery)
- Firmware repacking / patching: [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery)
- Hardware flashing (Level 3 Hard Brick): [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery)

---

## 1. Hardware UART Telemetry Tapping

### 1.1 Test Pad Locations

On both the X-T10 and FinePix X10 mainboards there are three labelled test pads near the SoC / flash corner. They are usually silk-screened on the PCB underside (bottom of the board, battery compartment side):

| Pad | Function | Notes |
|---|---|---|
| `TP_TX` | SoC UART transmit (camera → host) | 3.3 V LVCMOS push-pull output |
| `TP_RX` | SoC UART receive (host → camera) | 3.3 V LVCMOS input, weak pull-up |
| `GND` | Common ground | Use the pad adjacent to `TP_TX`, not the battery negative terminal, to avoid ground loops |

X-T10: pads sit between the EXR processor and the Wi-Fi module shield can. FinePix X10: pads sit beside the SPI flash U (Winbond/Macronix) and the SD-card slot.

### 1.2 Electrical Specifications

| Parameter | Value |
|---|---|
| Logic level | **3.3 V LVCMOS** |
| Baud rate | **115200 bps** |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 |
| Frame format | **115200 8N1** |
| Flow control | None (no RTS/CTS) |

### 1.3 Recommended Hardware

- **FTDI FT232RL** USB-TTL adapter (3.3 V mode, jumper set to 3.3 V) — preferred, low latency.
- **Raspberry Pi Pico** running a logic-analyzer / UART-bridge firmware (e.g. `pico-uart-bridge` or `sigrok` firmware) — good for capturing long traces.
- Any CP2102/CH340 adapter **only if** its VIO pin is strapped to 3.3 V.

**Warnings:**
- **Never use 5 V TTL.** Applying 5 V to `TP_RX`/`TP_TX` destroys the SoC I/O pads (the EXR/Milbeaut I/O is not 5 V tolerant). A 5 V adapter is the single most common cause of an otherwise-recoverable board becoming a Level 3 hard brick.
- Do not connect the adapter's `VCC`/`5V` pin to the camera. Power the camera from its own battery only.
- Keep the adapter and camera on the same USB hub only if the hub is powered; otherwise use a separate powered hub to avoid brown-outs.

### 1.4 Console Access

```bash
# Linux
picocom -b 115200 /dev/ttyUSB0
# or
screen /dev/ttyUSB0 115200
```

On power-on the bootloader prints the boot log, and on a fault prints the exception vector (e.g. `Data Abort Exception` with PC/LR addresses) before halting. Capture the full trace to a file for offline analysis.

### 1.5 Failure Mitigation (UART)

- **Floating noise / garbage characters:** Check ground continuity first. Connect `GND` pad → adapter GND with a short (< 10 cm) wire; re-seat the clip. Add a 100 nF capacitor between `TP_TX` and GND on the adapter side if ringing persists. Lower baud to 57600 only if the bootloader was rebuilt; stock firmware is fixed at 115200.
- **Camera refuses to power on while UART is connected:** Ground loop or back-feeding through the adapter's I/O protection diodes. Disconnect the adapter's `VCC` (already should be unconnected), then disconnect `TP_RX` (host→camera) while keeping `TP_TX`+GND for read-only telemetry. If it still fails, isolate the adapter on a separate USB port / powered hub and re-test. Persistent failure → remove all UART wiring and recover via [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery) (software) or [`#level-3-hard-brick--recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery) (hardware).

Mitigation links:
- Volatile/PTP RAM: [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery)
- Firmware repacking/patching: [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery)
- Hardware flashing: [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery)

---

## 2. In-Circuit SPI Flash Dumping & Debricking (Level 3 Hard Brick)

### 2.1 Target Chip

SOIC-8 SPI NOR flash, 128 Mbit (16 MB), one of:

| Part | Manufacturer | JEDEC ID |
|---|---|---|
| `W25Q128.V` | Winbond | `EF 40 18` |
| `MX25L128` | Macronix | `C2 20 18` |

Located on the mainboard beside the EXR processor. Verify the exact part number printed on the package before flashing.

### 2.2 SOIC-8 Pinout (top view, dot = pin 1)

```
        +-----+
  CS# 1 |     | 8 VCC
 SOI 2 |     | 7 HOLD#/IO3
 WP# 3 |     | 6 SCK
 GND 4 |     | 5 SO
        +-----+
```

| Pin | Name | Function |
|---|---|---|
| 1 | `CS#` | Chip select (active low) |
| 2 | `SOI` / `DI` | Data in (MOSI) |
| 3 | `WP#` | Write protect (tie high for normal op) |
| 4 | `GND` | Ground |
| 5 | `SO` / `DO` | Data out (MISO) |
| 6 | `SCK` | Serial clock |
| 7 | `HOLD#` / `IO3` | Hold (tie high) |
| 8 | `VCC` | 3.3 V supply |

### 2.3 Pomona 5250 Clip Attachment Procedure

1. Remove battery and lens. Open the rear/front shells per the service manual to expose the mainboard.
2. Locate the SPI flash U (SOIC-8 package). Clean the pins with IPA; verify pin 1 orientation (dot/dimple).
3. Attach the **Pomona 5250** SOIC-8 test clip so that its pin-1 marker aligns with the chip's pin-1 dot. Confirm all 8 contacts seat; re-seat if any pin floats.
4. **3.3 V VCC decoupling:** Place a 100 nF ceramic capacitor between `VCC` (pin 8) and `GND` (pin 4) at the clip leads; add a 10 µF electrolytic in parallel if the cable run is long. This suppresses the CH341A's switching noise.
5. **Capacitor draining:** Before attaching, discharge the mainboard's bulk capacitors: short `VCC` to `GND` through a 1 kΩ resistor for 10 s with the battery removed. Verify 0 V on `VCC` with a multimeter. Skipping this risks the programmer's LDO and the flash.
6. Keep the camera **unpowered** (no battery, no USB) during the entire procedure. The programmer supplies 3.3 V to the chip only.

### 2.4 flashrom Commands

Detect the chip:

```bash
flashrom -p ch341a_spi
```

Dump twice and compare for bit-rot / bad contact:

```bash
flashrom -p ch341a_spi -c "W25Q128.V" -r backup_1.bin
flashrom -p ch341a_spi -c "W25Q128.V" -r backup_2.bin
cmp backup_1.bin backup_2.bin
```

Rewrite with a clean stock dump to unbrick:

```bash
flashrom -p ch341a_spi -c "W25Q128.V" -w clean_stock_dump.bin
```

`flashrom` verifies automatically after writing (`VERIFIED`). For Macronix parts, substitute `-c "MX25L12835F"` (or the detected name) accordingly.

### 2.5 Failure Mitigation (SPI / Hardware)

- **`flashrom` reports "No EEPROM/flash device found":** Re-seat the Pomona clip; check pin-1 alignment; verify 3.3 V present on pin 8; discharge capacitors again; try a shorter USB cable.
- **`cmp` differs between dumps:** Bad clip contact or noise. Re-seat, add decoupling capacitor, re-dump until two identical reads.
- **Write fails / verify mismatch:** Confirm the chip is not write-protected (`WP#` high); disable any software write-protect via `flashrom --wp-disable` if supported; if the flash is permanently locked, the board requires chip replacement.
- **Camera still dead after successful write:** The bootloader region may be correct but the SoC OTP fuse / strap pins may be affected — escalate to UART telemetry (Section 1) to read the boot log. If no UART output and no power, treat as irrecoverable without SoC replacement.
- **Programmer overheats / VCC sags:** Stop immediately; check for a short on the mainboard (a shorted capacitor can drag VCC down). Do not force-write.

Mitigation links:
- Volatile/PTP RAM: [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery)
- Firmware repacking/patching: [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery)
- Hardware flashing: [`docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery)

---

## 3. Mitigation Matrix

| Symptom | Likely Cause | Mitigation Protocol |
|---|---|---|
| Boot loop (reboots every few seconds) | Corrupted RTOS kernel / bad firmware image | [`#firmware-level-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery) — DISP/BACK forced update with stock firmware |
| Frozen screen / no menu response | Hung task in injected code (RAM only) | [`#ptp-ram-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery) — pull battery 30 s; then [`#firmware-level-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery) if persistent |
| Battery drain (camera off but battery empties) | Stuck task / Wi-Fi stack not sleeping | [`#firmware-level-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery) — reflash stock; check for held GPIO |
| No power (no LED, no screen) | Bootloader/flash corruption or hardware short | [`#level-3-hard-brick--recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery) — SPI flash dump/rewrite; check shorts first |
| Corrupted OSD / garbage on screen | Framebuffer pointer corruption (RAM only) | [`#ptp-ram-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery) — power-cycle; code fix via cold hook |
| `FIRMWARE CORRUPTED` on update | Checksum mismatch | [`#firmware-level-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery) — recompute checksum (see brick doc Regla 2) |
| UART floating noise / garbage | Ground loop, missing decoupling | Section 1.5 above; then [`#ptp-ram-recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery) |
| `flashrom` no device found | Bad clip contact | Section 2.5 above; [`#level-3-hard-brick--recovery`](BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery) |
| Dump mismatch between reads | Noise / bad contact | Section 2.5; re-dump until identical |

---

## Cross-References

- Brick risk analysis, prevention & debricking: [`docs/BRICK_ANALYSIS_AND_RECOVERY.md`](BRICK_ANALYSIS_AND_RECOVERY.md)
- Hardware telemetry (this document): [`docs/HARDWARE_TELEMETRY_AND_RECOVERY.md`](HARDWARE_TELEMETRY_AND_RECOVERY.md)