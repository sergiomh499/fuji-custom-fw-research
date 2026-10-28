# Fujifilm X-T10 Firmware Memory Map & Internal Structures

Comprehensive reverse-engineering findings for **Fujifilm X-T10** (`FWUP0007.DAT`, v1.31, 53,084,624 bytes un-inverted ARM32 payload).

---

## 1. Film Simulation DSP Token Table

Located at physical file offset **`0x0024fb10 - 0x0024fb70`**:

The EXR Processor II image processing pipeline selects and switches film simulations using length-prefixed identifier tokens:

| Physical Offset | Length | Token | Film Simulation Mode |
|---|---|---|---|
| `0x0024fb1a` | 3 | `ILM` | Base prefix (`FILM`) |
| `0x0024fb22` | 6 | `_ASTIA` | Astia / Soft |
| `0x0024fb2b` | 3 | `BW_` | Monochrome / Black & White |
| `0x0024fb3b` | 6 | `CHROME` | Classic Chrome |
| `0x0024fb48` | 5 | `NEG_H` | Pro Neg. Hi |
| `0x0024fb54` | 4 | `PROV` | Provia / Standard |
| `0x0024fb5d` | 3 | `SEP` | Sepia |
| `0x0024fb63` | 3 | `VEL` | Velvia / Vivid |

---

## 2. UI State Machine Menu Table

Located at physical file offset **`0x00805dc0 - 0x0080c100`**:

The camera's on-screen menu system is controlled by a contiguous array of **507 entries**, each occupying a fixed **`0x32` bytes (50 bytes)** containing the uppercase internal menu identifier:

- **Table Base:** `0x00805dc0` (`RECSTART`)
- **Stride:** `0x32` (50 bytes) per entry

### Key Subsystem Menu Identifiers

| Index | Hex Index | Address | Menu Identifier | Function |
|---|---|---|---|---|
| 0 | `0x00` | `0x00805dc0` | `RECSTART` | Recording mode initialization |
| 213 | `0x0D5` | `0x008087be` | `SELFTIMERMODE` | Self-timer selection |
| 215 | `0x0D7` | `0x008087f0` | `ISOMENU` | ISO sensitivity selector |
| 216 | `0x0D8` | `0x00808822` | `WBMENU` | White Balance menu |
| 217 | `0x0D9` | `0x00808854` | `WBKEL` | WB Kelvin temperature manual select |
| 221 | `0x0DD` | `0x008088ea` | `AEMENU` | Autoexposure / Photometry metering |
| 222 | `0x0DE` | `0x0080891c` | `AFMENU` | Autofocus mode (AF-S / AF-C / MF) |
| **223** | `0x0DF` | **`0x0080894e`** | **`FSIMMENU`** | **Film Simulation selection menu** |
| 224 | `0x0E0` | `0x00808980` | `DRANGEMENU` | Dynamic Range (100%, 200%, 400%) |
| **225** | `0x0E1` | **`0x008089b2`** | **`CUSTOMMENU`** | **Custom settings / recipes (C1-C7)** |
| 232 | `0x0E8` | `0x00808b10` | `RECCONTMENU` | Continuous shooting / burst drive |
| 234 | `0x0EA` | `0x00808b74` | `SHUTTERTYPEMENU`| Mechanical (MS) vs Electronic (ES) |
| 250 | `0x0FA` | `0x00808e94` | `MOVIEREAD` | Video recording subsystem |
| 274 | `0x112` | `0x00809344` | `CUSTOMSAVEOK` | Custom recipe save confirmation |
| 282 | `0x11A` | `0x0080943e` | `FILMBKTSEL` | Film Simulation bracketing mode |

---

## 3. Custom Recipe Slots (C1 – C7)

UTF-16LE string and configuration matrices for the 7 custom user presets:

| Slot | Memory Offset | Label |
|---|---|---|
| `C1` | `0x01dcc3b2` | `CUSTOM 1` |
| `C2` | `0x01de40e2` | `CUSTOM 2` |
| `C3` | `0x01dd5e22` | `CUSTOM 3` |
| `C4` | `0x01dc0ca6` | `CUSTOM 4` |
| `C5` | `0x01dd8e06` | `CUSTOM 5` |
| `C6` | `0x01dc3f6e` | `CUSTOM 6` |
| `C7` | `0x01de4e4a` | `CUSTOM 7` |

---

## 4. Embedded SQLite Schema

Located at **`0x00bf34f0 - 0x00bf4500`**:

Fujifilm embeds SQLite to manage file system indexes, picture properties, and persistent flags:

- **`create table pt(pn text primary key,pcnt,lno)`** (`0x00bf34f0`)
  Tracks picture records, print counts (`pcnt`), and line order (`lno`).
- **`create table finf(fn text primary key,tm,s1,f1,f2,f3,f4,f5,f6,f7,f8)`** (`0x00bf3548`)
  Tracks file info: filename (`fn`), timestamp (`tm`), settings (`s1`), and feature flags (`f1` through `f8`).
- **`create table fct(fc primary key,fcnt)`** (`0x00bf4454`)
  Tracks file counters.


### Virtual Address Mapping & Pointer Table

The X-T10 firmware is mapped into virtual RAM with a fixed delta:
```
VIRTUAL_ADDRESS = PHYSICAL_FILE_OFFSET + 0x0135FFB8
```

Ghidra headless xref analysis verified the following virtual pointers:
- **`0x01F534A8`** (points to `SQLITE_TABLE_PT`): Found at file offset `0x00BF3494`.
- **`0x01F5440C`** (points to `SQLITE_TABLE_FCT`): Found at file offset `0x00BF3498`.
- **`0x01F53500`** (points to `SQLITE_TABLE_FINF`): Found in dispatch table at `0x021768C6` and `0x021768CA`.
---

## 5. Lens Mount Negotiation & Focus Stepping

- Lens mount protocol negotiation entry: `0x0056f172` (`START_NEGO`)
- Lens drive & focus status: `0x0056f000 - 0x0056f400`
- Shutter release entrypoint (FujiHack): `0x0096cc80` (`FIRM_TAKEPIC`)
