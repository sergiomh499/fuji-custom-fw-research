# Fujifilm DSP Color Pipeline (X-T10 v1.31)

## 1. Film Simulation Token Table

Located in the unpacked binary at `0x0024FB10 - 0x0024FB70`. Tokens are short
ASCII identifiers embedded in a compact serialized table:

| Token | Simulation |
|---|---|
| `PROV` | Provia (Standard) |
| `VEL` / `VELV` | Velvia (Vivid) |
| `_ASTIA` / `ASTIA` | Astia (Soft) |
| `CHROME` | Classic Chrome |
| `NEG_H` | Pro Neg. Hi |
| `BW_` / `BW` | Monochrome |
| `SEP` / `SEPIA` | Sepia |
| `ACROS` | Acros |
| `ETERNA` | Eterna |

## 2. Color Transform Matrix

Each token is followed by a 3x3 RGB->RGB color matrix:

```
[ R' ]   [ m00 m01 m02 ] [ R ]
[ G' ] = [ m10 m11 m12 ] [ G ]
[ B' ]   [ m20 m21 m22 ] [ B ]
```

- Storage: 9 x `int32` little-endian, immediately after the token (null
  terminators skipped, aligned to 4 bytes).
- Scaling: **Q12 fixed point**, i.e. divide by `4096` (`1 << 12`) to obtain
  the floating-point coefficient. Identity matrix is therefore
  `[4096,0,0, 0,4096,0, 0,0,4096]`.
- An IEEE-754 `float32` variant is also supported by the patcher when
  `dtype="f"` is requested.

## 3. Tone Curve LUT

Immediately after the 9 matrix coefficients (`matrix_offset + 9*4`) a 1-D tone
curve LUT follows. Entries are `int32` (Q12) or `float32` depending on the
variant. LUT length is target-specific; the extractor reports
`tone_lut_offset` for each descriptor.

## 4. Extraction Protocol

```python
from core.film_simulation import FilmSimulationExtractor

data = open("xt10_v131.bin", "rb").read()
ext = FilmSimulationExtractor(data)
for d in ext.extract_descriptors():
    print(d["token"], d["offset"], d["matrix"])
```

## 5. Injection / Transplant Protocol

```python
from core.film_simulation import FilmSimulationPatcher

patcher = FilmSimulationPatcher(data)
# Replace Provia matrix with Classic Chrome coefficients:
patcher.set_matrix("PROV", chrome_matrix_ints)
# Swap two simulations:
patcher.swap_matrices("PROV", "CHROME")
# Write custom tone curve LUT after the matrix:
patcher.inject_lut("PROV", lut_ints)
out = patcher.generate()   # bytes
```

Newer profiles (Classic Chrome, Eterna, Acros) can be constructed by supplying
a 9-element matrix (Q12 ints) and an optional LUT, then transplanting via
`set_matrix` / `inject_lut` or `swap_matrices`.

## 6. Injection Safety

- Always operate on an unpacked binary; repack with `FujiContainer.repack`.
- Keep a backup of the original `.DAT` and verify checksums.
- Incorrect matrices can produce invalid color output but are not destructive
  to boot; still, validate on a spare device first.
