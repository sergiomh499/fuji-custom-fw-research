# X-T5 (v4.31) Firmware Analysis — X-Processor 5 / X-Trans V HR

## Scope
Unpacked binary analysis performed by `core/xt5_extractor.py` (`XT5Extractor`).

Failure mitigation:
- Volatile / PTP RAM: `docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery`
- Firmware repacking / patching: `docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery`

## Film simulation token table (X-Processor 5)

| Token | Meaning |
|---|---|
| `NOSTALGIC_NEG` / `NEG_N` / `NOSTALGIC` | Nostalgic Neg |
| `BLEACH_BYPASS` / `ETERNA_BB` / `BYPASS` | Eterna Bleach Bypass |
| `REALA` / `REALA_ACE` | Reala ACE |
| `CLASSIC_NEG` / `NEG_C` | Classic Negative |
| `ETERNA` / `CINEMA` | Eterna / Eterna Cinema |
| `ACROS*` | Acros variants |
| `PROVIA`, `VELVIA`, `ASTIA`, `CLASSIC` (Chrome) | Standard set |

Tokens are short ASCII names embedded in menu/resource tables; the extractor
scans byte buffers and de-duplicates by offset keeping the longest token.

## 3x3 matrix representation
Matrices are stored as 9 x 32-bit little-endian integers in Q12 (scale 4096)
or Q15 (scale 32768), immediately following a token after zero-word padding,
with a 1-D tone LUT at `matrix_offset + 9*4`.

## Tone curve offsets
`tone_lut_offset = matrix_offset + 9*4` (default 4 values).

## Sensor resolution
40.2MP X-Trans CMOS V HR (APS-C): 7728 x 5152. The extractor scans for
`40.2MP`, `7728`, `5152`, `X-TRANS V` markers.

## Architecture header
X-Processor 5 markers: `X-Processor 5`, `XPROCESSOR5`, etc.
