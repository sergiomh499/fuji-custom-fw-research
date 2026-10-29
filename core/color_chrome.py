"""Color Chrome Effect and Color Chrome FX Blue for Fujifilm-style pipelines.

Implements selective saturation-aware tonal compression:

  * Color Chrome Effect: for highly saturated warm hues (reds, oranges,
    yellows, greens) the dominant channel is shoulder-compressed, restoring
    tonal gradation in deeply saturated regions.
  * Color Chrome FX Blue: for saturated blue/cyan sky hues
    (180 <= H <= 250 deg) the pixel is darkened without shifting white
    balance or affecting warm skin tones.

Saturation is estimated as::

    Sat(R, G, B) = (max(R,G,B) - min(R,G,B)) / (max(R,G,B) + eps)

Failure mitigation:
- Volatile / PTP RAM recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
- Firmware repacking / patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Sequence, Tuple, Union

BytesLike = Union[bytes, bytearray, memoryview, Sequence[int]]


def _norm_level(value: Any) -> "ColorChromeLevel":
    if isinstance(value, ColorChromeLevel):
        return value
    if isinstance(value, str):
        v = value.strip().upper().replace(" ", "_").replace("-", "_")
        try:
            return ColorChromeLevel[v]
        except KeyError:
            alias = {"NONE": "OFF", "LOW": "WEAK", "HIGH": "STRONG",
                     "MEDIUM": "WEAK", "MID": "WEAK"}
            if v in alias:
                return ColorChromeLevel[alias[v]]
    try:
        return ColorChromeLevel(int(value))
    except (TypeError, ValueError):
        pass
    raise ValueError(f"invalid Color Chrome level: {value!r}")


class ColorChromeLevel(enum.IntEnum):
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
            alias = {"NONE": "OFF", "LOW": "WEAK", "HIGH": "STRONG",
                     "MEDIUM": "WEAK"}
            if v in alias:
                return cls[alias[v]]
        return None


@dataclass
class ColorChromeConfig:
    chrome_level: ColorChromeLevel = ColorChromeLevel.OFF
    chrome_blue_level: ColorChromeLevel = ColorChromeLevel.OFF

    def __post_init__(self):
        self.chrome_level = _norm_level(self.chrome_level)
        self.chrome_blue_level = _norm_level(self.chrome_blue_level)


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
    raise TypeError("rgb_buffer must be a sequence or bytes-like object")


def rgb_to_hsv(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """Return (H in degrees, S in [0,1], V in [0,1]) for normalized RGB."""
    mx = max(r, g, b)
    mn = min(r, g, b)
    delta = mx - mn
    if mx == 0.0:
        return (0.0, 0.0, 0.0)
    s = delta / mx
    if delta == 0.0:
        h = 0.0
    elif mx == r:
        h = 60.0 * (((g - b) / delta) % 6.0)
    elif mx == g:
        h = 60.0 * (((b - r) / delta) + 2.0)
    else:
        h = 60.0 * (((r - g) / delta) + 4.0)
    if h < 0.0:
        h += 360.0
    return (h, s, mx)


class ColorChromeProcessor:
    """Apply Color Chrome Effect and Color Chrome FX Blue to RGB images."""

    _CHROME_FACTOR = {
        ColorChromeLevel.OFF: 0.0,
        ColorChromeLevel.WEAK: 0.12,
        ColorChromeLevel.STRONG: 0.28,
    }
    _BLUE_FACTOR = {
        ColorChromeLevel.OFF: 0.0,
        ColorChromeLevel.WEAK: 0.10,
        ColorChromeLevel.STRONG: 0.22,
    }
    _SAT_THRESHOLD = 0.25

    def __init__(self, *args, **kwargs) -> None:
        config = kwargs.pop("config", None)
        chrome_level = kwargs.pop("chrome_level", kwargs.pop("chrome", kwargs.pop("color_chrome", None)))
        chrome_blue_level = kwargs.pop("chrome_blue_level", kwargs.pop("chrome_blue", kwargs.pop("color_chrome_blue", kwargs.pop("chrome_fx_blue", None))))

        for a in args:
            if isinstance(a, (ColorChromeConfig, dict)):
                config = a
            elif chrome_level is None and isinstance(a, (str, ColorChromeLevel, int)):
                chrome_level = a
            elif chrome_blue_level is None and isinstance(a, (str, ColorChromeLevel, int)):
                chrome_blue_level = a

        if config is not None:
            if isinstance(config, dict):
                chrome_level = config.get("chrome_level", config.get("chrome", chrome_level))
                chrome_blue_level = config.get("chrome_blue_level", config.get("chrome_blue", chrome_blue_level))
            else:
                chrome_level = getattr(config, "chrome_level", chrome_level)
                chrome_blue_level = getattr(config, "chrome_blue_level", chrome_blue_level)

        self.config = ColorChromeConfig(
            chrome_level=chrome_level if chrome_level is not None else ColorChromeLevel.OFF,
            chrome_blue_level=chrome_blue_level if chrome_blue_level is not None else ColorChromeLevel.OFF,
        )
        self.chrome_level = self.config.chrome_level
        self.chrome_blue_level = self.config.chrome_blue_level

    def process_pixel(self, r: Any, g: Any, b: Any) -> Tuple[int, int, int]:
        r0, g0, b0 = int(r), int(g), int(b)
        if self.chrome_level == ColorChromeLevel.OFF and self.chrome_blue_level == ColorChromeLevel.OFF:
            return (r0, g0, b0)

        rf, gf, bf = r0 / 255.0, g0 / 255.0, b0 / 255.0
        h, s, v = rgb_to_hsv(rf, gf, bf)

        out_r, out_g, out_b = rf, gf, bf

        # Color Chrome Effect: warm saturated hues.
        if self.chrome_level != ColorChromeLevel.OFF and s > self._SAT_THRESHOLD and (h <= 120.0 or h >= 300.0):
            factor = self._CHROME_FACTOR[self.chrome_level]
            channels = [out_r, out_g, out_b]
            di = max(range(3), key=lambda i: channels[i])
            mx = max(channels)
            mn = min(channels)
            reduction = (mx - mn) * factor
            channels[di] = max(mn, channels[di] - reduction)
            out_r, out_g, out_b = channels

        # Color Chrome FX Blue: blue/cyan sky hues.
        if self.chrome_blue_level != ColorChromeLevel.OFF and self._SAT_THRESHOLD < s and 180.0 <= h <= 250.0:
            factor = self._BLUE_FACTOR[self.chrome_blue_level]
            mult = 1.0 - factor
            out_r *= mult
            out_g *= mult
            out_b *= mult

        return (
            int(round(max(0.0, min(1.0, out_r)) * 255.0)),
            int(round(max(0.0, min(1.0, out_g)) * 255.0)),
            int(round(max(0.0, min(1.0, out_b)) * 255.0)),
        )

    def process_image(self, rgb_buffer: Any, width: int, height: int) -> bytes:
        width = int(width)
        height = int(height)
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        vals = _flatten(rgb_buffer)
        n = width * height * 3
        if len(vals) != n:
            raise ValueError(f"buffer length {len(vals)} != width*height*3 {n}")
        out = bytearray()
        for i in range(0, len(vals), 3):
            r, g, b = self.process_pixel(vals[i], vals[i + 1], vals[i + 2])
            out.extend((r, g, b))
        return bytes(out)

    # aliases
    def process(self, r, g, b):
        return self.process_pixel(r, g, b)

    def apply_pixel(self, r, g, b):
        return self.process_pixel(r, g, b)

    def apply(self, rgb_buffer, width, height):
        return self.process_image(rgb_buffer, width, height)


# module-level aliases
ColorChrome = ColorChromeProcessor
ColorChromeEffect = ColorChromeProcessor
