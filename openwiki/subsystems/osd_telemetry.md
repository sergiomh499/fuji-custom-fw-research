---
type: concept
title: OSD Framebuffer & Live Telemetry
description: Architecture of the Fujifilm X-T10 On-Screen Display (OSD) framebuffer, liveview overlay injection, and volatile USB PTP memory telemetry.
tags: [osd, framebuffer, telemetry, ptp, usb, liveview]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-28T21:29:05.191Z
sources:
  - id: openwiki-source-5d83d196e134a3bb9228dfd9
    resource: repo://core/osd.py
  - id: openwiki-source-2ccb5705e779e7586992312a
    resource: repo://core/ptp.py
generated: { by: "omp", at: "2026-10-28T21:29:05.191Z" }
---

# OSD Framebuffer & Live Telemetry

Real-time user feedback during shooting requires inspecting and writing to the camera's display buffers and volatile system memory without flashing non-volatile storage.

## OSD Framebuffer Memory Mapping

The Fujifilm X-T10 manages On-Screen Display (OSD) graphics separately from raw sensor Bayer pipelines:
- **Display Resolution:** $640 \times 480$ pixels.
- **Pixel Encoding:** RGB565 (16 bits per pixel) or packed YUV422.
- **Buffer Size:** 307,200 bytes per frame plane.
- **Debug Routine:** Physical offset `0x007F9C1C` (`OSD DEBUG MODE SCREEN SELECT`).
- **Buffer Pointer:** Virtual RAM address `0x01B59BD4`.

The `core/osd.py` module models this display plane, supporting:
1. **Framing Guides:** Rule of thirds, 16:9 widescreen crops, 2.39:1 anamorphic markers, **65:24 Hasselblad XPan panoramic letterbox**, and **1:1 square medium-format pillarbox**.
2. **Zebra Stripes:** Overexposure warning masks computed on pixels exceeding a given luma threshold ($Y \ge 235$).
3. **Peaking Masks:** High-contrast edge detection highlights for manual focusing.
4. **Status Text:** Custom overlays displaying telemetry (battery millivolts, CPU temperature).
5. **2-Axis Electronic Horizon:** Real-time roll ($\theta$) and pitch ladder projection; line transitions to level green (`0x07E0`) when $|\theta| \le 0.5^\circ$.
6. **False Color IRE Scale:** Video exposure visualization mapping luminance to standardized IRE color bands (purple clipped blacks, blue shadows, green 18% gray, pink skin tones, red clipped highlights).
The corresponding standalone ARMv7-A payload in `payloads/osd_overlay/` writes test patterns directly to the buffer descriptor with zero overhead.

## PTP/USB Live Volatile RAM Telemetry

Picture Transfer Protocol (PTP / ISO 15740) provides a non-destructive gateway to read and write camera memory:
- **Dispatcher Routine:** `FIRM_PTP` at `0x01E7C718`.
- **Target Vendor Opcodes:**
  - `0x9028`: Read volatile memory range (`address`, `length`).
  - `0x9029`: Write volatile memory buffer (`address`, `data`).
  - `0x902A`: Execute arbitrary code at address.
- **Staging Buffer:** `0x01CF0000 - 0x01CF4000` (unused volatile DRAM region).

The client utility `tools/fuji_ptp.py` communicates with the camera over standard USB:
```bash
# Read 256 bytes from DRAM staging area
python3 tools/fuji_ptp.py read 0x01cf0000 256

# Dump a 64 KB memory block to disk
python3 tools/fuji_ptp.py dump ram_dump.bin --start 0x01cf0000 --size 65536
```

Because operations target volatile DRAM, any unexpected execution hang is fully mitigated by cutting power: pulling the battery resets the memory state with zero risk to on-board flash.
