---
type: concept
title: Recipe Persistence (C1-C7) & SD Card Exchange
description: Serialization of Fujifilm custom film simulation recipes (C1-C7) in EEPROM binary structs and human-readable SD card exchange format.
tags: [recipes, eeprom, sd-card, serialization, c1-c7, custom-settings]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-28T21:29:05.191Z
sources:
  - id: openwiki-source-5ad8f445c501e698afa589fb
    resource: repo://core/recipe.py
  - id: openwiki-source-c4d5496e30629639c339221a
    resource: repo://docs/RECIPE_STORAGE_SPEC.md
generated: { by: "omp", at: "2026-10-28T21:29:05.191Z" }
---

# Recipe Persistence (C1-C7) & SD Card Exchange

Fujifilm cameras allow photographers to store custom shooting configurations in 7 distinct preset slots labeled `CUSTOM 1` through `CUSTOM 7` (`C1` to `C7`). In firmware, these slots are represented as fixed-size packed binary records stored in non-volatile EEPROM and mapped into volatile DRAM upon boot.

## EEPROM Binary Record Layout

Each custom recipe is packed into a 128-byte little-endian structure:

| Offset | Type | Field | Description |
|---|---|---|---|
| `0x00 - 0x03` | `char[4]` | `magic` | Identifier bytes (`FJRC`) |
| `0x04` | `uint8` | `version` | Schema version (`1`) |
| `0x05` | `uint8` | `slot_id` | Slot index (`0` for C1, ..., `6` for C7) |
| `0x06` | `uint8` | `film_sim` | Base simulation (0=Provia, 1=Velvia, 2=Astia, 3=Classic Chrome, etc.) |
| `0x07` | `uint8` | `dynamic_range` | Dynamic range code (0=DR100, 1=DR200, 2=DR400) |
| `0x08` | `uint8` | `wb_mode` | White balance mode (0=Auto, 1=Daylight, ..., 8=Kelvin, 9=Custom) |
| `0x09 - 0x0A`| `uint16_le` | `wb_kelvin` | Color temperature in Kelvin (2500–10000 K) |
| `0x0B` | `int8` | `wb_shift_r` | White balance Red shift ($-9$ to $+9$) |
| `0x0C` | `int8` | `wb_shift_b` | White balance Blue shift ($-9$ to $+9$) |
| `0x0D` | `int8` | `highlight_tone`| Highlight tone adjustment ($-2$ to $+2$) |
| `0x0E` | `int8` | `shadow_tone` | Shadow tone adjustment ($-2$ to $+2$) |
| `0x0F` | `int8` | `color` | Color saturation adjustment ($-2$ to $+2$) |
| `0x10` | `int8` | `sharpness` | Edge sharpness adjustment ($-2$ to $+2$) |
| `0x11` | `int8` | `noise_reduct` | High ISO noise reduction ($-2$ to $+2$) |
| `0x12 - 0x31`| `char[32]` | `name` | Null-terminated UTF-8 custom recipe title |
| `0x32 - 0x7B`| `bytes[74]` | `reserved` | Future expansion fields (grain, clarity, color chrome) |
| `0x7C - 0x7F`| `uint32_le` | `crc32` | CRC-32 integrity checksum over bytes 0x00–0x7B |

## Human-Readable SD Card Exchange Format

To enable photographers to share and backup recipes using plain text files on the SD card (`/DCIM/RECIPES/RECIPE1.TXT`), `core/recipe.py` implements an INI-style serialization:

```ini
[recipe]
name = Kodachrome 64
base_simulation = Classic Chrome
dynamic_range = 400
white_balance = daylight
wb_shift_red = 2
wb_shift_blue = -4
highlight_tone = -1
shadow_tone = 1
color = 1
sharpness = 1
noise_reduction = -2
```

The `RecipeBank` class provides bi-directional conversion: it validates parameter constraints, computes the CRC-32 checksum, and unpacks SD card text files directly into the camera's binary EEPROM memory layout.
