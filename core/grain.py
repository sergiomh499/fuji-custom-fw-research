"""Procedural film grain synthesis (X-Trans III/IV/V "Grain Effect").

Reverse-engineered behaviour notes:
  * Roughness / Strength: OFF, WEAK, STRONG.
  * Size: SMALL, LARGE (introduced X-Trans IV).
  * Silver-halide density response: grain peaks in midtones (Zone V) and rolls
    off in deep shadows / high highlights:
        W(L) = 4 * L * (1 - L),  L in [0, 1].

Failure mitigation:
  * Grain is applied to volatile image buffers only (never flash/PTP RAM):
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
  * Any firmware-level patching of grain tables follows:
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

import enum
import math
import random
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple, Union

BytesLike = Union[bytes, bytearray, memoryview, List[int]]


class GrainRoughness(enum.IntEnum):
    OFF = 0
    WEAK = 1
    STRONG = 2

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            v = value.strip().upper().replace(" ", "_").replace("-", "_")
            for m in cls:
                if m.name == v:
                    return m
            # common aliases
            alias = {"NONE": "OFF", "LOW": "WEAK", "HIGH": "STRONG",
                     "MEDIUM": "WEAK"}
            if v in alias:
                return cls[alias[v]]
        return None


class GrainSize(enum.IntEnum):
    SMALL = 0
    LARGE = 1

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            v = value.strip().upper().replace(" ", "_").replace("-", "_")
            for m in cls:
                if m.name == v:
                    return m
            alias = {"S": "SMALL", "L": "LARGE", "FINE": "SMALL", "COARSE": "LARGE"}
            if v in alias:
                return cls[alias[v]]
        return None


def _norm_roughness(v):
    if isinstance(v, GrainRoughness):
        return v
    try:
        return GrainRoughness(v)
    except (ValueError, KeyError):
        return GrainRoughness.WEAK if v else GrainRoughness.OFF


def _norm_size(v):
    if isinstance(v, GrainSize):
        return v
    try:
        return GrainSize(v)
    except (ValueError, KeyError):
        return GrainSize.SMALL


def density_weight(luma: float) -> float:
    """Film density response curve W(L) = 4*L*(1-L)."""
    L = float(luma)
    if L < 0.0:
        L = 0.0
    if L > 1.0:
        L = 1.0
    return 4.0 * L * (1.0 - L)


# aliases
film_density_response = density_weight
density_curve = density_weight
grain_density_weight = density_weight
W = density_weight


@dataclass
class GrainConfig:
    strength: GrainRoughness = GrainRoughness.WEAK
    size: GrainSize = GrainSize.SMALL
    seed: int = 0
    midtone_peak_modulation: float = 1.0
    # common aliases kept as fields for compatibility
    midtone_peak: float = field(default=None)
    peak_modulation: float = field(default=None)
    modulation: float = field(default=None)

    def __post_init__(self):
        self.strength = _norm_roughness(self.strength)
        self.size = _norm_size(self.size)
        # resolve midtone peak modulation aliases
        for cand in (self.midtone_peak, self.peak_modulation, self.modulation):
            if cand is not None:
                self.midtone_peak_modulation = float(cand)
                break
        if self.midtone_peak is None:
            self.midtone_peak = self.midtone_peak_modulation
        if self.peak_modulation is None:
            self.peak_modulation = self.midtone_peak_modulation
        if self.modulation is None:
            self.modulation = self.midtone_peak_modulation
        # normalize seed
        self.seed = int(self.seed) & 0xFFFFFFFF

    @property
    def roughness(self):
        return self.strength

    @roughness.setter
    def roughness(self, v):
        if v is not None:
            self.strength = _norm_roughness(v)

    @property
    def grain_size(self):
        return self.size

    @grain_size.setter
    def grain_size(self, v):
        if v is not None:
            self.size = _norm_size(v)

    @property
    def roughness(self):  # type: ignore
        return self.strength

    @roughness.setter
    def roughness(self, v):
        if v is not None:
            self.strength = _norm_roughness(v)


class GrainSynthesizer:
    """Deterministic procedural film grain generator."""

    _ROUGHNESS_AMP = {
        GrainRoughness.OFF: 0.0,
        GrainRoughness.WEAK: 0.06,
        GrainRoughness.STRONG: 0.14,
    }

    def __init__(self, config=None, **kwargs):
        if config is None:
            # accept flat kwargs
            cfg = GrainConfig(
                strength=kwargs.get("strength", kwargs.get("roughness", GrainRoughness.WEAK)),
                size=kwargs.get("size", kwargs.get("grain_size", GrainSize.SMALL)),
                seed=kwargs.get("seed", 0),
                midtone_peak_modulation=kwargs.get("midtone_peak_modulation",
                                                  kwargs.get("midtone_peak",
                                                             kwargs.get("peak_modulation", 1.0))),
            )
            self.config = cfg
        elif isinstance(config, GrainConfig):
            self.config = config
        else:
            # maybe config is a seed int
            if isinstance(config, int):
                self.config = GrainConfig(seed=config, **{k: v for k, v in kwargs.items()})
            else:
                self.config = GrainConfig(**{**config, **kwargs}) if isinstance(config, dict) else GrainConfig(config, **kwargs)
        self._rng = random.Random(self.config.seed)

    # convenience accessors
    @property
    def seed(self):
        return self.config.seed

    @property
    def strength(self):
        return self.config.strength

    @property
    def size(self):
        return self.config.size

    def _lattice_step(self):
        return 2 if self.config.size == GrainSize.SMALL else 4

    def _hash(self, x, y):
        # integer hash lattice
        n = x * 374761393 + y * 668265263 + self.config.seed * 1274126177
        n = (n ^ (n >> 13)) * 1274126177
        n = n ^ (n >> 16)
        return (n & 0xFFFFFFFF) / 0xFFFFFFFF

    def _smooth_noise(self, x, y):
        step = self._lattice_step()
        # coordinate in lattice
        fx = x / step
        fy = y / step
        x0 = math.floor(fx)
        y0 = math.floor(fy)
        x1 = x0 + 1
        y1 = y0 + 1
        tx = fx - x0
        ty = fy - y0
        # smoothstep
        sx = tx * tx * (3 - 2 * tx)
        sy = ty * ty * (3 - 2 * ty)
        n00 = self._hash(x0, y0)
        n10 = self._hash(x1, y0)
        n01 = self._hash(x0, y1)
        n11 = self._hash(x1, y1)
        a = n00 + (n10 - n00) * sx
        b = n01 + (n11 - n01) * sx
        return a + (b - a) * sy

    def _gaussian_noise(self, u1, u2):
        # Box-Muller
        r = math.sqrt(-2.0 * math.log(max(u1, 1e-12)))
        theta = 2.0 * math.pi * u2
        return r * math.cos(theta)

    def generate_grain_pattern(self, width, height):
        """Return a 2D list (height x width) of grain values in [-1, 1]."""
        amp = self._ROUGHNESS_AMP.get(self.config.strength, 0.0)
        if amp == 0.0:
            return [[0.0 for _ in range(width)] for _ in range(height)]
        pat = [[0.0 for _ in range(width)] for _ in range(height)]
        for y in range(height):
            for x in range(width):
                u1 = self._smooth_noise(x, y)
                u2 = self._smooth_noise(x + 97, y + 131)
                g = self._gaussian_noise(max(u1, 1e-6), u2)
                pat[y][x] = g
        return pat

    # alias returning flat
    def generate_grain_flat(self, width, height):
        pat = self.generate_grain_pattern(width, height)
        return [v for row in pat for v in row]

    def _luma_from_rgb(self, r, g, b):
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0

    def apply_to_buffer(self, buffer, width, height, fmt="luma"):
        """Apply grain to buffer in place. Supports fmt='luma' or 'rgb'."""
        if self.config.strength == GrainRoughness.OFF:
            return buffer
        pat = self.generate_grain_pattern(width, height)
        amp = self._ROUGHNESS_AMP.get(self.config.strength, 0.0)
        mod = self.config.midtone_peak_modulation
        if fmt == "luma":
            for y in range(height):
                for x in range(width):
                    idx = y * width + x
                    val = int(buffer[idx])
                    L = val / 255.0
                    w = density_weight(L) * mod
                    nv = int(round(val + pat[y][x] * w * amp * 255.0))
                    nv = max(0, min(255, nv))
                    buffer[idx] = nv
        else:  # rgb
            for y in range(height):
                for x in range(width):
                    idx = (y * width + x) * 3
                    r = int(buffer[idx]); g = int(buffer[idx+1]); b = int(buffer[idx+2])
                    L = self._luma_from_rgb(r, g, b)
                    w = density_weight(L) * mod
                    grain = pat[y][x] * w * amp
                    for c in range(3):
                        v = int(buffer[idx + c])
                        nv = int(round(v + grain * 255.0 * 0.5))
                        nv = max(0, min(255, nv))
                        buffer[idx + c] = nv
        return buffer
        pat = self.generate_grain_pattern(width, height)
        amp = self._ROUGHNESS_AMP.get(self.config.strength, 0.0)
        # work on list copy if needed
        try:
            buf = buffer
            # detect mutable sequence
            mutable = True
        except Exception:
            mutable = False

        if fmt == "luma":
            # one byte per pixel
            for y in range(height):
                for x in range(width):
                    idx = y * width + x
                    val = int(buffer[idx]) if hasattr(buffer, "__getitem__") else 0
                    L = val / 255.0
                    w = density_weight(L) * self.config.midtone_peak_modulation
                    grain = pat[y][x] * w
                    new_val = int(round(val + grain * 255.0 * amp * 2.0))  # amp already in pat? adjust
                    # avoid double amp: pat includes amp, so just add
                    new_val = int(round(val + pat[y][x] * w * 255.0))
                    new_val = max(0, min(255, new_val))
                    if hasattr(buffer, "__setitem__"):
                        buffer[idx] = new_val
        else:  # rgb
            # 3 bytes per pixel
            for y in range(height):
                for x in range(width):
                    idx = (y * width + x) * 3
                    r = int(buffer[idx])
                    g = int(buffer[idx + 1])
                    b = int(buffer[idx + 2])
                    L = self._luma_from_rgb(r, g, b)
                    w = density_weight(L) * self.config.midtone_peak_modulation
                    grain = pat[y][x] * w
                    for c in range(3):
                        v = int(buffer[idx + c])
                        nv = int(round(v + grain * 255.0 * 0.5))
                        nv = max(0, min(255, nv))
                        if hasattr(buffer, "__setitem__"):
                            buffer[idx + c] = nv
        return buffer


# module-level aliases for common method names
GrainSynthesizer.density_weight = lambda self, luma: density_weight(luma)
GrainSynthesizer.film_density_response = lambda self, luma: density_weight(luma)
GrainSynthesizer.density_curve = lambda self, luma: density_weight(luma)
GrainSynthesizer.W = lambda self, luma: density_weight(luma)
