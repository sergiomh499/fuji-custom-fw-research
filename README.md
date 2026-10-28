# Fujifilm Custom Firmware Research (`fuji-custom-fw-research`)

Research repository, tooling, and memory mapping for reverse-engineering and modifying Fujifilm camera firmware:
- **Fujifilm X-T10** (EXR Processor II / X-Trans CMOS II)
- **Fujifilm FinePix X10** (1st Gen EXR Processor / 2/3" EXR-CMOS)

> **Disclaimer & Legal Framework (Spain / EU):**
> This repository contains **NO proprietary Fujifilm firmware files or copyright-protected binary dumps**. 
> All research is conducted strictly under **Articles 100.3, 100.4, and 100.5 of the Spanish Intellectual Property Law (LPI)** and **EU Directive 2009/24/EC Articles 5/6** (Interoperability and Study of Computer Programs, affirmed by CJEU Case C-406/10).
> Tools operate exclusively in clean-room local mode: users obtain official firmware updates directly from Fujifilm's distribution servers, and patches are computed on-the-fly.
> 
- Detailed legal analysis: [docs/LEGAL_AND_COMPLIANCE.md](docs/LEGAL_AND_COMPLIANCE.md)
- AI Agent guidelines & pre-commit validation checklist: [AGENTS.md](AGENTS.md)
- Brick risk analysis, prevention & debricking guide: [docs/BRICK_ANALYSIS_AND_RECOVERY.md](docs/BRICK_ANALYSIS_AND_RECOVERY.md)
- Hardware telemetry, UART pinouts & flashrom recovery: [docs/HARDWARE_TELEMETRY_AND_RECOVERY.md](docs/HARDWARE_TELEMETRY_AND_RECOVERY.md)
- Technical roadmap & next steps: [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md)
---

## 1. Firmware Architecture Overview

Fujifilm digital cameras use an unencrypted but bit-flipped package format for firmware updates (`FWUPxxxx.DAT`).

### Header Layout (Type 4: X-T10 & Modern X Series)

| Byte Range | Type | Field | Description |
|---|---|---|---|
| `0x000 - 0x003` | `uint32_le` | `type` | Header OS/Type layout (e.g. `0x04`) |
| `0x004 - 0x203` | `bytes[512]` | `code` | Model code; ASCII characters interleaved every 2 bytes |
| `0x204 - 0x207` | `uint32_le` | `v1` | Firmware version major (e.g. `1` in `1.31`) |
| `0x208 - 0x20B` | `uint32_le` | `v2` | Firmware version minor (e.g. `0x31` for `1.31`) |
| `0x20C - 0x20F` | `uint32_le` | `checksum` | Additive check value across inverted payload |
| `0x210 - 0x213` | `uint32_le` | `end` | End marker / device type |
| `0x214 - EOF` | `bytes` | `payload` | **Bitwise NOT (`~byte`)** ARM32 machine code and data |

Total header size for Type 4: **532 bytes** (`512 + 20`).

---

## 2. Model Specifics: Fujifilm X-T10

- **Processor:** EXR Processor II
- **Sensor:** 16.3 MP X-Trans CMOS II
- **Architecture:** ARM 32-bit Little-Endian
- **Latest Official Firmware:** `v1.31` (`FWUP0007.DAT`, July 2018)
- **Model Code:** `0005100100051002000510040005100500051007000510090005101`

### Known Memory Offsets (v1.31)

Extracted from static analysis and FujiHack symbol stubs:

| Symbol / Routine | Memory / Text Offset | Purpose |
|---|---|---|
| `FIRM_TAKEPIC` | `0x0096cc80` | Entry point executed when shutter button triggers a capture |
| `FIRM_PTP` | `0x01e7c718` | USB Picture Transfer Protocol (PTP) request dispatcher |
| `OUT_OF_MEMORY_CODE` | `0x00bd8954` | SQLite error handler reference |
| `OUT_OF_MEMORY_REF` | `0x01f54c3c` | Runtime virtual RAM reference |
| `OUT_OF_MEMORY_REAL` | `0x00bf4c84` | Physical text offset in dumped flash |
| `OSD_DEBUG_SCREEN` | `0x007f9c1c` | On-Screen Display debug screen routine |


---

## 3. Model Specifics: Fujifilm FinePix X10

- **Processor:** EXR Processor (1st Generation)
- **Sensor:** 12.0 MP 2/3-inch EXR-CMOS (28-112mm f/2.0-2.8 manual zoom barrel)
- **Architecture:** ARM 32-bit Little-Endian
- **Latest Official Firmware:** `v2.01` (`FPUPDATE.DAT`, October 2015, ~25.8 MB)
- **Model Code:** `00010221000102220001022300010224000102250001022600010227000102280001022900010235`
- **Sister Target:** Identical platform to **Fujifilm XF1** where `CAN_CUSTOM_FIRMWARE`, `PRINTIM_HACK`, and `IMG_PROPS_HACK` were validated in FujiHack.
- **Detailed Guide:** See [docs/X10_ARCHITECTURE.md](docs/X10_ARCHITECTURE.md).
---

## 4. Tooling (`tools/fuji_fw.py`)

A zero-dependency Python 3 utility to inspect, decrypt, disassemble-prepare, and repack firmware:


### Download Official Firmware Directly
```bash
# Download Fujifilm X-T10 official v1.31 (FWUP0007.DAT)
python3 tools/fuji_fw.py download xt10

# Download Fujifilm X10 official v2.01 (FPUPDATE.DAT)
python3 tools/fuji_fw.py download x10
```
### Inspect Firmware Header
```bash
python3 tools/fuji_fw.py info FWUP0007.DAT
```

### Unpack to Raw ARM32 Binary (for Ghidra / IDA / Radare2)
```bash
python3 tools/fuji_fw.py unpack FWUP0007.DAT xt10_v131.bin
# Generates xt10_v131.bin and xt10_v131.json (metadata)
```

### Scan Keywords & Symbols
```bash
python3 tools/fuji_fw.py scan xt10_v131.bin --filter film,focus,provia,menu --limit 30
```

### Repack Modified Binary with Checksum Recalculation
```bash
python3 tools/fuji_fw.py repack xt10_v131_mod.bin xt10_v131.json FWUP0007_PATCHED.DAT --increment-version
```

### Automated Ghidra Headless Analysis
```bash
# Launch Ghidra analyzeHeadless with automatic symbol and table labeling
python3 tools/ghidra_headless.py \
  --target xt10 \
  --bin xt10_v131.bin \
  --project-dir ./ghidra_project \
  --script ghidra_scripts/LabelFujifilmStructures.py
```

### Binary Patch & Trampoline Injection
```bash
# Calculate relative ARM32 branch instruction between addresses
python3 tools/fuji_patch.py branch 0x00485258 0x01cf0000 --link

# Inject payload and trampoline into unpacked binary
python3 tools/fuji_patch.py inject xt10_v131.bin payloads/payload.bin 0x00485258 0x01cf0000 xt10_v131_mod.bin
```

### Bare-Metal Payload Toolchain (`payloads/`)
```bash
# Check compiler status and build bare-metal ARM payloads
make -C payloads check
make -C payloads payload.bin   # Build for X-T10 (ARMv7-A)
make -C payloads x10           # Build for X10 (ARMv5TE)
```

---

## 5. Reverse Engineering Roadmap

- [x] Initial header parsing and payload bit-flip decrypter.
- [x] Checksum recalculator for repacking modified payloads.
- [x] Mapped Film Simulation DSP tokens (`PROV`, `VEL`, `CHROME`, `_ASTIA`).
- [x] Mapped 507-entry UI State Machine Menu Table (`FSIMMENU`, `AFMENU`, `CUSTOMMENU`).
- [x] Automated Ghidra headless analyzer wrapper and labeling script.
- [x] ARM32 bare-metal payload harness, linker script, and relative branch injector.
- [x] Deep reverse engineering of DSP color matrix tables and 3x3 transform coefficients (`core/film_simulation.py`, `docs/COLOR_PIPELINE.md`).
- [x] Wi-Fi KASAGO TCP/IP crash analysis and defensive patch for modern Android 14+/iOS 18 devices (`core/wifi_patch.py`, `docs/WIFI_STACK_CRASH_ANALYSIS.md`).
- [x] Map lens focus stepping functions and Snap Focus payload for Ricoh GR style instant focus jump (`payloads/snap_focus/`, `docs/X_MOUNT_LENS_PROTOCOL.md`).
- [x] Reverse engineer custom film recipe serialization (C1-C7) and SD card recipe exchange (`core/recipe.py`, `docs/RECIPE_STORAGE_SPEC.md`).
- [x] PTP USB live telemetry and volatile RAM dumper client (`core/ptp.py`, `tools/fuji_ptp.py`, mitigation: `docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery`).
- [x] OSD framebuffer overlay engine and position-independent ARMv7-A payload (`core/osd.py`, `payloads/osd_overlay/`, mitigation: `docs/BRICK_ANALYSIS_AND_RECOVERY.md#cold-hooking`).
- [x] FinePix X10 EXR 1st Gen architecture analyzer and signature scanner (`core/x10_analyzer.py`, `fujitool analyze x10`).
- [x] 3D-LUT to Fuji DSP matrix & 1D tone curve compiler (`core/lut_compiler.py`, `tools/lut_compiler.py`).
- [x] Physical UART telemetry pinout and in-circuit SPI flashrom debricking runbook (`docs/HARDWARE_TELEMETRY_AND_RECOVERY.md`).
