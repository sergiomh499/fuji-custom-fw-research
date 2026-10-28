---
type: guide
title: Quickstart & Workflow Guide
description: Step-by-step developer guide for installing dependencies, downloading official firmware, unpacking, repacking, and running the test suite.
tags: [quickstart, guide, fujitool, cli, workflow, testing]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-28T21:29:05.191Z
sources:
  - id: openwiki-source-93c4bf642ecfa683655a01ec
    resource: repo://cli/main.py
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "omp", at: "2026-10-28T21:29:05.191Z" }
---

# Quickstart & Workflow Guide

The `fuji-custom-fw-research` repository operates under clean-room principles: it distributes zero proprietary firmware binaries or copyrighted dumps. Instead, tools automatically download official firmware updates directly from Fujifilm's distribution servers and perform analysis and patching locally.

## Prerequisites & Environment Setup

The repository requires Python 3.9+ and standard GNU utilities. To compile bare-metal ARM payloads, the bare-metal GCC toolchain is required:

```bash
# Arch Linux / CachyOS
sudo pacman -S arm-none-eabi-gcc arm-none-eabi-newlib

# Debian / Ubuntu
sudo apt install gcc-arm-none-eabi
```

Clone the repository and verify the environment:
```bash
git clone https://github.com/sergiomh499/fuji-custom-fw-research.git
cd fuji-custom-fw-research
python3 -m unittest discover tests
```

## The Unified CLI (`fujitool`)

The `fujitool` executable provides a single entrypoint for container inspection, decryption, repacking, patching, and model-specific analysis.

### 1. Downloading Official Firmware
Download official firmware `.DAT` files directly from Fujifilm:
```bash
# Download official v1.31 firmware for Fujifilm X-T10
./fujitool download xt10 -o /tmp/FWUP0007.DAT

# Download official v2.01 firmware for FinePix X10
./fujitool download x10 -o /tmp/FPUPDATE.DAT
```

### 2. Inspecting Container Metadata
Inspect header layouts, OS types, model code strings, and checksums:
```bash
./fujitool info /tmp/FWUP0007.DAT
```

### 3. Unpacking and Decrypting
Unpack the bit-inverted `.DAT` container into a raw 32-bit ARM binary and a JSON sidecar:
```bash
./fujitool unpack /tmp/FWUP0007.DAT xt10_v131.bin
```

### 4. Scanning for System Identifiers
Scan the unpacked binary for menu identifiers, film simulation tokens, and network symbols:
```bash
./fujitool scan xt10_v131.bin --filter film,provia,focus,menu --limit 20
```

### 5. Applying Defensive Patches & Repacking
Apply the Wi-Fi crash patch to prevent camera freezing with modern Android 14+/iOS 18 devices and recalculate the checksum:
```bash
./fujitool patch wifi /tmp/FWUP0007.DAT /tmp/FWUP0007_PATCHED.DAT --increment-version
```

### 6. Model-Specific Analysis
Run automated architectural checks and symbol identification on the unpacked binary:
```bash
./fujitool analyze xt10 xt10_v131.bin
./fujitool analyze x10 x10_v201.bin
```

## Developer Navigation Map

| Topic / Subsystem | Wiki Page | Core Source Files |
|---|---|---|
<!-- openwiki: broken internal link [/openwiki/architecture/firmware_container.md] link "/openwiki/architecture/firmware_container.md" is root-absolute, which no real consumer resolves against the repository root (not a coding agent reading the page, not GitHub's Markdown renderer, not a local viewer); use a path relative to this file instead. Fix the href or restore the target, then delete this comment. -->
| **Firmware Packaging** | [Firmware Container Architecture](/openwiki/architecture/firmware_container.md) | `core/container.py`, `core/checksum.py` |
<!-- openwiki: broken internal link [/openwiki/subsystems/color_pipeline.md] link "/openwiki/subsystems/color_pipeline.md" is root-absolute, which no real consumer resolves against the repository root (not a coding agent reading the page, not GitHub's Markdown renderer, not a local viewer); use a path relative to this file instead. Fix the href or restore the target, then delete this comment. -->
| **Color Science** | [DSP Film Simulation & Color Pipeline](/openwiki/subsystems/color_pipeline.md) | `core/film_simulation.py`, `core/lut_compiler.py` |
<!-- openwiki: broken internal link [/openwiki/subsystems/wifi_networking.md] link "/openwiki/subsystems/wifi_networking.md" is root-absolute, which no real consumer resolves against the repository root (not a coding agent reading the page, not GitHub's Markdown renderer, not a local viewer); use a path relative to this file instead. Fix the href or restore the target, then delete this comment. -->
| **Wi-Fi Crash Fix** | [KASAGO TCP/IP Stack & Wi-Fi Crash](/openwiki/subsystems/wifi_networking.md) | `core/wifi_patch.py` |
<!-- openwiki: broken internal link [/openwiki/subsystems/lens_and_focus.md] link "/openwiki/subsystems/lens_and_focus.md" is root-absolute, which no real consumer resolves against the repository root (not a coding agent reading the page, not GitHub's Markdown renderer, not a local viewer); use a path relative to this file instead. Fix the href or restore the target, then delete this comment. -->
| **Lens Control** | [X-Mount Lens Protocol & Snap Focus](/openwiki/subsystems/lens_and_focus.md) | `payloads/snap_focus/` |
<!-- openwiki: broken internal link [/openwiki/subsystems/recipe_persistence.md] link "/openwiki/subsystems/recipe_persistence.md" is root-absolute, which no real consumer resolves against the repository root (not a coding agent reading the page, not GitHub's Markdown renderer, not a local viewer); use a path relative to this file instead. Fix the href or restore the target, then delete this comment. -->
| **Custom Recipes** | [Recipe Persistence (C1-C7)](/openwiki/subsystems/recipe_persistence.md) | `core/recipe.py` |
<!-- openwiki: broken internal link [/openwiki/subsystems/osd_telemetry.md] link "/openwiki/subsystems/osd_telemetry.md" is root-absolute, which no real consumer resolves against the repository root (not a coding agent reading the page, not GitHub's Markdown renderer, not a local viewer); use a path relative to this file instead. Fix the href or restore the target, then delete this comment. -->
| **Live Telemetry** | [OSD Framebuffer & Telemetry](/openwiki/subsystems/osd_telemetry.md) | `core/osd.py`, `core/ptp.py` |
<!-- openwiki: broken internal link [/openwiki/hardware/safety_and_mitigation.md] link "/openwiki/hardware/safety_and_mitigation.md" is root-absolute, which no real consumer resolves against the repository root (not a coding agent reading the page, not GitHub's Markdown renderer, not a local viewer); use a path relative to this file instead. Fix the href or restore the target, then delete this comment. -->
| **Hardware Recovery** | [Safety & Debricking Runbook](/openwiki/hardware/safety_and_mitigation.md) | `docs/BRICK_ANALYSIS_AND_RECOVERY.md` |
<!-- openwiki: broken internal link [/openwiki/workflows/patching_and_repacking.md] link "/openwiki/workflows/patching_and_repacking.md" is root-absolute, which no real consumer resolves against the repository root (not a coding agent reading the page, not GitHub's Markdown renderer, not a local viewer); use a path relative to this file instead. Fix the href or restore the target, then delete this comment. -->
| **Binary Patching** | [Patching & Ghidra Toolchains](/openwiki/workflows/patching_and_repacking.md) | `core/patcher.py`, `ghidra_scripts/` |
