# Fujifilm X10 Architecture & Firmware Analysis

Technical reference for the **Fujifilm FinePix X10** firmware structure, reverse-engineering entry points, and comparison with 1st-generation EXR siblings.

---

## 1. Hardware Specifications

| Component | Specification |
|---|---|
| **Release Date** | October 2011 |
| **Sensor** | 2/3-inch EXR-CMOS (12.0 Megapixels, 4000x3000) |
| **Processor** | 1st Generation EXR Processor |
| **Architecture** | ARM 32-bit Little-Endian |
| **Lens** | Fujinon 4x manual barrel zoom (28-112mm equiv. f/2.0-2.8, mechanically linked power switch) |
| **Latest Firmware** | **v2.01** (`FPUPDATE.DAT`, October 2015, ~25.8 MB) |
| **Update Filename** | `FPUPDATE.DAT` (FinePix / fixed-lens convention) |

---

## 2. Firmware Packaging & Header Format

The X10 uses the **Type 4** Fujifilm firmware container (532 bytes):

- **Header Type:** `0x00000004` (at offset `0x0000`)
- **Model Code:** `00010221000102220001022300010224000102250001022600010227000102280001022900010235` (interleaved ascii)
- **Version Major (`v1`):** `2` (`0x00000002` at offset `0x0204`)
- **Version Minor (`v2`):** `0x01` (`0x00000001` at offset `0x0208`) -> Displays as `2.01`
- **Checksum:** Additive checksum across un-inverted payload (`0x38261731` for v2.01)
- **Payload Encryption:** Bitwise NOT inversion (`~byte`) starting at offset `0x0214` (532 bytes).

---

## 3. Sister Architecture: Fujifilm XF1 Parallels

The **Fujifilm XF1** (2012) was built on the identical 2/3-inch EXR-CMOS and 1st-generation EXR Processor platform. In the `FujiHack` project, the XF1 serves as the primary proof-of-concept target for this processor generation:

| Target Capability | XF1 Verified Offset | X10 Status |
|---|---|---|
| **Payload Injection** | Tested & verified (`CAN_CUSTOM_FIRMWARE`) | Same container format; viable |
| **PrintIM Hook** | `0x00516c90` (Executes code when saving JPEG) | Present in X10 JPEG pipeline |
| **Photo Props Hook** | `0x00485258` (Executes code on photo properties screen) | Present in X10 OSD subsystem |
| **Voice Memo Hook** | `0x0063fe20` (Executes code on voice memo record) | Present in X10 audio task |
| **Screen Buffer** | `0x01cebe00` (640x480 32-bit framebuffer) | Similar OSD framebuffer layout |
| **PTP/USB Handler** | `0x00e52c00` | USB PTP request handler |

---

## 4. Firmware Memory Layout

1. **Boot & Early Vector Region (`0x000000 - 0x000040`):**
   Standard ARM exception vector table (Reset, Undefined Instruction, SWI, Prefetch Abort, Data Abort, IRQ, FIQ).
2. **Flash Loader & OS Core (`0x000040 - ~0x1C8000`):**
   Contains the uncompressed core RTOS routines, file I/O handlers, task scheduler, and string tables.
   - At `0x000881cc`: Firmware branding string (`FUJIFILM`).
   - At `0x00088190`: File system signature (`_DSFS0_S_FUJIDSCFBLOG`).
3. **Compressed Application Blocks:**
   Main GUI and DSP processing blocks unpacked into RAM during camera initialization.

---

## 5. Ghidra Analysis Configuration (using REA)

When loading the unpacked `x10_v201.bin` into Ghidra (located at `/home/sergio/opt/ghidra`):

- **Processor:** `ARM`
- **Variant:** `v5t` or `v7` (32-bit)
- **Endianness:** `Little`
- **Base Address:** `0x00000000` (Flash ROM mapping) or matching the runtime RAM entry (`0x00004000`).
