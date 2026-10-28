# Fujifilm Custom Firmware Research (`fuji-custom-fw-research`)

Research repository, tooling, and memory mapping for reverse-engineering and modifying Fujifilm camera firmware:
- **Fujifilm X-T10** (EXR Processor II / X-Trans CMOS II)
- **Fujifilm FinePix X10** (1st Gen EXR Processor / 2/3" EXR-CMOS)

> **Disclaimer & Legal Notice:**
> This repository contains **NO proprietary Fujifilm firmware files or copyright-protected binary dumps**. 
> All research is conducted under legal interoperability provisions (EU Directive 2009/24/EC Articles 5/6, US DMCA §1201 exemptions). Tools operate strictly in clean-room local mode: users obtain official firmware updates directly from Fujifilm's distribution servers, and patches are computed on-the-fly.

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

---

## 5. Reverse Engineering Roadmap

- [x] Initial header parsing and payload bit-flip decrypter.
- [x] Checksum recalculator for repacking modified payloads.
- [ ] Locate Film Simulation LUT color matrix buffers (Provia, Velvia, Astia, Classic Chrome).
- [ ] Map lens focus stepping functions for manual focus Snap Focus.
- [ ] Implement USB PTP RAM dumper payload for live telemetry without flashing flash memory.
