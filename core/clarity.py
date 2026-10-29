"""Edge-preserving "Clarity" filter for Fujifilm-style DSP luminance pipelines.

Implements an unsharp-mask detail boost/softening pass:

    I_out = I + k * (I - I_base)

where ``I_base`` is an edge-preserving (bilateral) low-frequency
representation of the luminance plane and ``k = clarity * 0.2``.

Failure mitigation:
- Volatile / PTP RAM recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
- Firmware repacking / patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

import math
from typing import Any, Sequence, Union

BytesLike = Union[bytes, bytearray, memoryview]


def _flatten(buffer: Any) -> list:
    if isinstance(buffer, (bytes, bytearray, memoryview)):
        return [int(v) for v in buffer]
    if isinstance(buffer, Sequence):
        out: list = []
        for row in buffer:
            if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
                out.extend(_flatten(row))
            else:
                out.append(row)
        return out
    raise TypeError("luma_buffer must be a sequence or bytes-like object")


class ClarityFilter:
    """Apply Fujifilm-style Clarity to a grayscale/luminance plane."""

    def __init__(
        self,
        clarity_level: int = 0,
        radius: int = 3,
        sigma_spatial: float = 1.5,
        sigma_range: float = 0.1,
    ) -> None:
        self.clarity_level = self._validate_level(clarity_level)
        self.radius = int(radius)
        self.sigma_spatial = float(sigma_spatial)
        self.sigma_range = float(sigma_range)

    @staticmethod
    def _validate_level(level: Any) -> int:
        try:
            iv = int(level)
        except (TypeError, ValueError):
            raise ValueError("clarity_level must be an integer in [-5, 5]")
        if isinstance(level, float) and level != iv:
            raise ValueError("clarity_level must be an integer in [-5, 5]")
        if iv < -5 or iv > 5:
            raise ValueError("clarity_level must be in [-5, 5]")
        return iv

    def _to_plane(self, buffer: Any, width: int, height: int) -> list:
        vals = _flatten(buffer)
        n = width * height
        if len(vals) != n:
            raise ValueError(f"buffer length {len(vals)} != width*height {n}")
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        if isinstance(buffer, (bytes, bytearray, memoryview)):
            scale = 255.0
        elif any(isinstance(v, float) for v in vals):
            scale = 1.0
        else:
            scale = 1.0 if (vals and all(v in (0, 1) for v in vals)) else 255.0
        return [max(0.0, min(1.0, float(v) / scale)) for v in vals]

    def _bilateral_base(self, plane: list, width: int, height: int) -> list:
        r = self.radius
        ss = self.sigma_spatial
        sr = self.sigma_range
        inv_ss2 = 1.0 / (2.0 * ss * ss) if ss > 0 else 0.0
        inv_sr2 = 1.0 / (2.0 * sr * sr) if sr > 0 else 0.0
        out = [0.0] * len(plane)
        for y in range(height):
            for x in range(width):
                ci = y * width + x
                center = plane[ci]
                s = 0.0
                wsum = 0.0
                for dy in range(-r, r + 1):
                    ny = y + dy
                    if ny < 0 or ny >= height:
                        continue
                    for dx in range(-r, r + 1):
                        nx = x + dx
                        if nx < 0 or nx >= width:
                            continue
                        ni = ny * width + nx
                        nv = plane[ni]
                        spatial = math.exp(-(dx * dx + dy * dy) * inv_ss2)
                        diff = center - nv
                        rng = math.exp(-(diff * diff) * inv_sr2)
                        w = spatial * rng
                        s += nv * w
                        wsum += w
                out[ci] = s / wsum if wsum > 0 else center
        return out

    @staticmethod
    def _soft_knee_clamp(v: float, knee: float = 0.08) -> float:
        if v <= 0.0:
            return 0.0
        if v >= 1.0:
            return 1.0
        if v < knee:
            return (v * v) / (2.0 * knee)
        if v > 1.0 - knee:
            return 1.0 - ((1.0 - v) ** 2) / (2.0 * knee)
        return v

    def apply(
        self,
        luma_buffer: Any,
        width: int,
        height: int,
        clarity_level: int = None,
    ) -> bytes:
        if clarity_level is None:
            clarity_level = self.clarity_level
        level = self._validate_level(clarity_level)
        self.clarity_level = level

        width = int(width)
        height = int(height)
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")

        plane = self._to_plane(luma_buffer, width, height)

        if level == 0:
            return bytes(int(round(v * 255.0)) for v in plane)

        k = level * 0.2
        if k > 1.0:
            k = 1.0
        if k < -1.0:
            k = -1.0

        base = self._bilateral_base(plane, width, height)

        out_plane = [0.0] * len(plane)
        for i, (iv, bv) in enumerate(zip(plane, base)):
            detail = iv - bv
            val = iv + k * detail
            if k > 0:
                val = self._soft_knee_clamp(val)
            else:
                val = max(0.0, min(1.0, val))
            out_plane[i] = max(0.0, min(1.0, val))

        return bytes(int(round(v * 255.0)) for v in out_plane)


Clarity = ClarityFilter
ClarityEffect = ClarityFilter
