# X-T20 (v2.11) Firmware Analysis

## ACROS Film Simulation

Tokens scanned by `core/xt20_extractor.py` (`ACROS_TOKENS`):

| Token | Variant |
|---|---|
| `ACROS` | Acros Standard |
| `ACROS_YE` | Acros+Ye |
| `ACROS_R` | Acros+R |
| `ACROS_G` | Acros+G |
| `BW_` | Monochrome |
| `MONO` | Monochrome |

Layout follows the X-T10 film-simulation descriptor convention:
token (ASCII) -> zero-word padding -> 9 x int32 matrix -> tone LUT.
Matrices are 3x3 RGB->RGB transforms stored as 32-bit little-endian fixed point,
Q12 (scale 4096) by default; Q15 (scale 32768) is also observed for some
profiles. `matrix_offset` points at the first coefficient; `tone_lut_offset`
is `matrix_offset + 9*4`.

Representative token hits in `/tmp/xt20_v211.bin`:
- `FSIM_ACROS` @ 0x003A8788 (descriptor table region)
- `SET_ACROS` @ 0x003AF63E
- `FS_ACROS` @ 0x003B3FE3 (with `Y/R/G` filter suffixes)

## Wi-Fi Stack / Official v2.11 Freeze Fix

Unpatched X-T10 v1.31 crash sites:
- `recv Memory Depletiion Err.` @ 0x00B4DD9C
- `STM AP_SOC Halt.` @ 0x00B4DF3C

In X-T20 v2.11 the KASAGO stack is still present (`lanInit`, `efTcpIpInit`,
`tfDhcpdStart`) around 0x00F5F1B0-0x00F5FB38, but the official fix guards
the socket allocation path used for DHCP option 61 / SSDP discovery, preventing
the recv-memory-depletion halt. `XT20Extractor.analyze_wifi()` reports marker
offsets; `compare_wifi_with_xt10()` records the unpatched reference offsets
above.

Failure mitigation:
- Firmware repacking/patching: `docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery`
- Volatile/PTP RAM recovery: `docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery`
