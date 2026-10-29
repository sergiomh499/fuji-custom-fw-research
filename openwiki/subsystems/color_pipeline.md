---
type: concept
title: DSP Film Simulation & Color Pipeline
description: Reverse-engineered architecture of Fujifilm DSP color transformation matrices, Q12/Q15 fixed-point arithmetic, 1D tone curves, and 3D-LUT compilation.
tags: [color, dsp, film-simulation, matrix, lut, x-t10]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-28T21:29:05.191Z
sources:
  - id: openwiki-source-a874f64da62f6847fb9b22be
    resource: repo://core/film_simulation.py
  - id: openwiki-source-1195e89fe54335002a345722
    resource: repo://core/lut_compiler.py
generated: { by: "omp", at: "2026-10-28T21:29:05.191Z" }
---

# DSP Film Simulation & Color Pipeline

Fujifilm's color science on EXR Processor II and X-Trans sensors is executed in hardware DSP pipelines before image compression. The camera converts demosaiced sensor signals into finalized sRGB/AdobeRGB output through a sequence of linear $3 \times 3$ color space transform matrices followed by non-linear 1D tone transfer curves (LUTs).

## Film Simulation Token Table

In the unpacked binary of the Fujifilm X-T10 (`FWUP0007.DAT` v1.31), the core film simulation descriptors reside in the range `0x0024FB10 - 0x0024FB70`. Each entry is identified by an ASCII token:

| Token | Simulation Profile | Characteristics |
|---|---|---|
| `PROV` | Provia / Standard | Baseline neutral color rendering |
| `VEL` / `VELV` | Velvia / Vivid | Saturated primaries, high-contrast greens/blues |
| `_ASTIA` / `ASTIA` | Astia / Soft | Soft skin tones, saturated warm highlights |
| `CHROME` / `CLASSIC` | Classic Chrome | Muted saturation, warm greenish shadows |
| `NEG_H` | PRO Neg. Hi | Studio portraiture, punchier tone curve |
| `NEG_S` | PRO Neg. Std | Soft studio portraiture, subtle skin graduation |
| `BW_` / `BW` | Monochrome | Luminance channel conversion |
| `SEP` / `SEPIA` | Sepia | Monochrome with warm duotone shift |

## Matrix Mathematics and Representation

The transformation from sensor color space $(R_{in}, G_{in}, B_{in})$ to simulation color space $(R_{out}, G_{out}, B_{out})$ is performed using a $3 \times 3$ matrix:

$$\begin{bmatrix} R_{out} \\ G_{out} \\ B_{out} \end{bmatrix} = \begin{bmatrix} M_{00} & M_{01} & M_{02} \\ M_{10} & M_{11} & M_{12} \\ M_{20} & M_{21} & M_{22} \end{bmatrix} \begin{bmatrix} R_{in} \\ G_{in} \\ B_{in} \end{bmatrix}$$

In firmware memory, the 9 coefficients are stored as signed 32-bit little-endian integers using fixed-point representation:
- **Q12 format (default):** Scale factor $4096 = 1.0$.
- **Q15 format (high precision):** Scale factor $32768 = 1.0$.

Directly following the 9 matrix integers ($9 \times 4 = 36$ bytes), the DSP references a 1D tone curve table controlling highlight and shadow roll-off.

## 3D-LUT Compiler & Profile Injection

The `core/lut_compiler.py` and `tools/lut_compiler.py` modules allow compiling standard `.cube` 3D-LUTs into Fujifilm DSP matrix and tone curve representations:

1. **Least-Squares Fit:** Evaluates primary and secondary color coordinates from the 3D cube to solve the closest linear $3 \times 3$ matrix.
2. **Coefficient Clamping:** Constrains values to valid fixed-point bounds to prevent integer overflow in DSP registers.
3. **Tone Curve Fitting:** Derives highlight and shadow spline points from the neutral gray axis $(R=G=B)$.
4. **Binary Patching:** `core/film_simulation.py` (`FilmSimulationPatcher`) writes the new matrix coefficients over unused or low-priority slots (such as Sepia or Monochrome filters) without modifying adjacent camera code.

### Built-in Modern Presets

The LUT compiler provides built-in pre-calibrated matrix and tone curve profiles for modern Fujifilm film simulations:
- **Classic Negative:** High contrast, greenish-cyan shadows, warm highlights (Superia 400).
- **Eterna Cinema:** Flat dynamic cinema profile with soft highlight rolloff and desaturated tones.
- **Eterna Bleach Bypass:** Extreme tonal contrast with desaturated primary colors.
- **Nostalgic Neg:** Amber warm highlights, rich cyan sky rendering (1970s American new color).
- **Acros:** Enhanced monochrome luminance weights with extended shadow graduation.
- **Reala ACE:** Natural true-to-life color rendering with neutral greens and deep reds.

## Procedural Grain Effect Engine

Modern Fujifilm bodies (X-Trans III and newer) feature hardware-assisted procedural film grain. In `core/grain.py`:
- **Roughness Modes:** `OFF`, `WEAK`, `STRONG`.
- **Grain Sizes:** `SMALL`, `LARGE`.
- **Density Curve Response:** Real silver-halide film grain concentrates in the midtones (Zone V) and rolls off in deep shadows and bright specular highlights. The engine weights noise injection using parabolic luminance modulation:
  $$W(L) = 4 \cdot L \cdot (1 - L), \quad L \in [0, 1]$$
- **Determinism:** Seeded PRNG ensures identical texture across identical image frames while avoiding visible repeating grid artifacts.
