# X-T30 (v2.01) Firmware Analysis — X-Processor 4 / X-Trans IV

## Scope
Unpacked binary: `/tmp/xt30_v201.bin` (48 MiB). Analysis performed by
`core/xt30_extractor.py` (`XT30Extractor`).

Failure mitigation:
- Volatile / PTP RAM: `docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery`
- Firmware repacking / patching: `docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery`

## Film simulation token layout
Tokens are short ASCII names embedded in the menu/resource tables (around
`0x0043xxxx`–`0x0044xxxx` in the unpacked image). Observed plaintext
tokens and offsets:

| Token | Meaning | Offset(s) (hex) |
|---|---|---|
| `PROVIA` | Provia/Standard | `0x004492831` (also `0x004494268`, `0x004497424`) |
| `NEG_H` | Pro Neg. Hi | `0x004492858`, `0x004494301`, `0x004495315` |
| `NEG_C` | Classic Negative (menu token) | `0x011F131D` |
| `C_CHROM` / `CHROM` | Classic Chrome | `0x0044770B`, `0x00448E61`, `0x004493D1` |
| `VELV` / `VEL` | Velvia | `0x004486FA` (`VELV`), plus multiple `VEL` |
| `ACROS` | Acros | `0x00445867`, `0x00445D6D` |

`CLASSIC`, `CLASSIC_NEG`, `ETERNA`, `CINEMA`, `COLOR_CHROME`,
`CHROME_EFFECT`, and `FX_BLUE` are **not present as contiguous plaintext**
in this unpacked image; they are either packed in compressed menu resources
or referenced via DSP microcode labels. The extractor therefore treats them
as scan targets and reports zero hits on this build rather than inventing
offsets.

## 3x3 color transform matrices
Matrices are stored as 9 × 32-bit little-endian integers in Q12 (scale
4096), immediately following a token after zero-word padding, with a 1-D
tone LUT at `matrix_offset + 9*4`. Compared with the X-Trans II Provia
baseline (`[4096, 0, 0, 0, 4096, 0, 0, 0, 4096]` identity-ish), the
X-Processor 4 entries are embedded in menu/DSP tables and the plaintext
hits above are dominated by menu label runs, so matrix extraction on this
build is best-effort and should be cross-checked against the DSP bank
(`0x0043xxxx` region) in Ghidra.

## Color Chrome saturation compression
Software constants (from `core/color_chrome.py`, `ColorChromeProcessor`):

- Saturation threshold: `0.25`
- Warm hue ranges: `H <= 120°` or `H >= 300°`
- Blue hue range: `180° <= H <= 250°`
- Chrome factors: weak `0.12`, strong `0.28`
- Blue factors: weak `0.10`, strong `0.22`

Extracted marker offsets in the firmware: `COLOR_CHROME`/`CHROME`/`C_CHROM`
at `0x0044770B`, `0x00448E61`, `0x004493D1` (and `CHROM`-containing
menu labels throughout `0x00437C0B`–`0x004493D3`).
