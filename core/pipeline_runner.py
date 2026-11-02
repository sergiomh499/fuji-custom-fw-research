"""Modern Fujifilm image-processing pipeline runner.

Executes the complete pipeline:
  1. White balance tint & shift (wb_shift_r, wb_shift_b)
  2. 3x3 color matrix transform (film simulation)
  3. Color Chrome Effect & Chrome FX Blue saturation compression
  4. Clarity filter
  5. 1D tone curve (highlight / shadow)
  6. Procedural grain effect (midtone parabolic weighting)

Supports P6 binary PPM and raw ``RGBRGB...`` bytearrays (zero deps).

Failure mitigation:
- Volatile / PTP RAM recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
- Firmware repacking / patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from core.recipe import Recipe, FILM_SIM_NAMES
from core.color_chrome import ColorChromeProcessor, ColorChromeLevel
from core.clarity import ClarityFilter
from core.grain import GrainSynthesizer, GrainConfig, GrainRoughness, GrainSize, density_weight
from core.lut_compiler import PRESETS_FULL

BytesLike = Union[bytes, bytearray, memoryview, Sequence[int]]


def _as_bytes(data: Any) -> bytes:
    if data is None:
        return b""
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    if hasattr(data, "data"):
        return bytes(data.data)
    return bytes(data)


def _clamp(v: float, lo: float = 0.0, hi: float = 255.0) -> int:
    if v < lo:
        v = lo
    if v > hi:
        v = hi
    return int(round(v))


IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]

FILM_SIM_MATRICES: Dict[str, List[float]] = {
    "provia": IDENTITY[:],
    "standard": IDENTITY[:],
    "velvia": [1.25, -0.15, -0.10, -0.10, 1.20, -0.10, -0.10, -0.10, 1.10],
    "astia": [1.05, -0.03, -0.02, -0.02, 1.03, -0.01, -0.02, -0.01, 1.00],
    "classic chrome": [0.85, 0.15, 0.00, 0.10, 0.80, 0.10, 0.00, 0.10, 0.90],
    "classic_chrome": [0.85, 0.15, 0.00, 0.10, 0.80, 0.10, 0.00, 0.10, 0.90],
    "pro neg. hi": [1.05, -0.04, -0.01, -0.02, 1.02, 0.00, -0.03, 0.00, 0.98],
    "pro_neg_hi": [1.05, -0.04, -0.01, -0.02, 1.02, 0.00, -0.03, 0.00, 0.98],
    "pro neg. std": [1.00, -0.02, 0.00, 0.00, 1.00, 0.00, 0.00, 0.00, 0.98],
    "pro_neg_std": [1.00, -0.02, 0.00, 0.00, 1.00, 0.00, 0.00, 0.00, 0.98],
    "monochrome": [0.299, 0.587, 0.114, 0.299, 0.587, 0.114, 0.299, 0.587, 0.114],
    "bw": [0.299, 0.587, 0.114, 0.299, 0.587, 0.114, 0.299, 0.587, 0.114],
    "sepia": [0.393, 0.769, 0.189, 0.349, 0.686, 0.168, 0.272, 0.534, 0.131],
    "acros": [0.299, 0.587, 0.114, 0.299, 0.587, 0.114, 0.299, 0.587, 0.114],
    "eterna": [0.92, -0.02, -0.01, -0.01, 0.90, -0.02, -0.02, -0.01, 0.88],
    "classic negative": None,  # filled from preset
    "classic_neg": None,
    "nostalgic neg": None,
    "nostalgic_neg": None,
    "reala ace": None,
    "reala_ace": None,
}


def _preset_matrix(name: str) -> List[float]:
    for key in PRESETS_FULL:
        if key.lower().replace(" ", "") == name.lower().replace(" ", ""):
            return list(PRESETS_FULL[key]["matrix_float"])
    return IDENTITY[:]


for _k in ("classic negative", "classic_neg", "nostalgic neg", "nostalgic_neg", "reala ace", "reala_ace"):
    _name = _k.replace("_", " ").title()
    # map to preset title
    _lookup = {"classic negative": "Classic Negative", "classic neg": "Classic Negative",
               "classic_neg": "Classic Negative",
               "nostalgic neg": "Nostalgic Neg", "nostalgic_neg": "Nostalgic Neg",
               "nostalgic neg": "Nostalgic Neg",
               "reala ace": "Reala ACE", "reala_ace": "Reala ACE",
               "reala ace": "Reala ACE"}[_k]
    FILM_SIM_MATRICES[_k] = _preset_matrix(_lookup)


def _matrix_for(sim: Any) -> List[float]:
    if isinstance(sim, (list, tuple)) and len(sim) == 9:
        return [float(x) for x in sim]
    if isinstance(sim, int):
        name = FILM_SIM_NAMES.get(sim, "Provia")
    else:
        name = str(sim)
    key = name.strip().lower().replace(" ", "_").replace(".", "").replace("-", "_")
    # try direct
    if key in FILM_SIM_MATRICES and FILM_SIM_MATRICES[key] is not None:
        return FILM_SIM_MATRICES[key][:]
    # try spaced
    key2 = name.strip().lower()
    if key2 in FILM_SIM_MATRICES and FILM_SIM_MATRICES[key2] is not None:
        return FILM_SIM_MATRICES[key2][:]
    # preset lookup
    for pk in PRESETS_FULL:
        if pk.lower().replace(" ", "_") == key or pk.lower() == key2:
            return list(PRESETS_FULL[pk]["matrix_float"])
    return IDENTITY[:]


def _norm_level_str(v):
    if v is None:
        return "OFF"
    return str(v)


class PipelineRunner:
    """Run the modern Fujifilm image processing pipeline on RGB bytes.

    Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
    Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
    """

    def __init__(
        self,
        image: Any = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        *,
        recipe: Any = None,
        simulation: Any = None,
        film_simulation: Any = None,
        grain: Any = None,
        grain_size: Any = None,
        clarity: int = 0,
        chrome_level: Any = None,
        chrome_blue_level: Any = None,
        color_chrome: Any = None,
        color_chrome_blue: Any = None,
        wb_shift_r: int = 0,
        wb_shift_b: int = 0,
        highlight: int = 0,
        shadow: int = 0,
        color: int = 0,
        seed: int = 0,
        **kwargs,
    ) -> None:
        # allow image to be a Recipe
        if isinstance(image, Recipe):
            recipe = image
            image = None

        # allow tuple (w, h, data)
        if isinstance(image, (tuple, list)) and len(image) == 3 and isinstance(image[2], (bytes, bytearray, memoryview, list)):
            width = int(image[0])
            height = int(image[1])
            image = image[2]

        self.width = width
        self.height = height
        self.image = _as_bytes(image) if image is not None else b""

        # infer square if possible
        if (self.width is None or self.height is None) and self.image:
            n = len(self.image) // 3
            import math as _m
            s = int(round(_m.sqrt(n)))
            if s * s == n:
                self.width = s
                self.height = s
            else:
                self.width = self.width or 0
                self.height = self.height or 0

        if recipe is not None:
            self.recipe = recipe if isinstance(recipe, Recipe) else None
        else:
            self.recipe = None
        # if recipe object passed via kwargs
        if self.recipe is None and "recipe" in kwargs and isinstance(kwargs["recipe"], Recipe):
            self.recipe = kwargs["recipe"]

        # derive from recipe
        if self.recipe is not None:
            if simulation is None and film_simulation is None:
                simulation = self.recipe.film_simulation
            if wb_shift_r == 0:
                wb_shift_r = self.recipe.wb_shift_r
            if wb_shift_b == 0:
                wb_shift_b = self.recipe.wb_shift_b
            if highlight == 0:
                highlight = self.recipe.highlight
            if shadow == 0:
                shadow = self.recipe.shadow
            if color == 0:
                color = self.recipe.color

        self.simulation = simulation if simulation is not None else (film_simulation if film_simulation is not None else "Provia")
        if film_simulation is not None:
            self.simulation = film_simulation

        self.grain = grain
        self.grain_size = grain_size if grain_size is not None else "SMALL"
        self.clarity = int(clarity) if clarity is not None else 0
        self.chrome_level = chrome_level if chrome_level is not None else (color_chrome if color_chrome is not None else "OFF")
        self.chrome_blue_level = chrome_blue_level if chrome_blue_level is not None else (color_chrome_blue if color_chrome_blue is not None else "OFF")
        self.wb_shift_r = int(wb_shift_r)
        self.wb_shift_b = int(wb_shift_b)
        self.highlight = int(highlight)
        self.shadow = int(shadow)
        self.color = int(color)
        self.seed = int(seed)
        self.kwargs = kwargs

    # ---------- I/O ----------
    @staticmethod
    def read_ppm(path: Union[str, Path]) -> Tuple[int, int, bytes]:
        with open(path, "rb") as f:
            magic = f.readline().strip()
            if magic != b"P6":
                raise ValueError("not a P6 PPM file")
            line = f.readline()
            while line.startswith(b"#") or line.strip() == b"":
                line = f.readline()
            w, h = (int(x) for x in line.split()[:2])
            # maxval
            mv_line = f.readline()
            while mv_line.startswith(b"#") or mv_line.strip() == b"":
                mv_line = f.readline()
            maxval = int(mv_line.strip())
            if maxval != 255:
                raise ValueError("only 8-bit PPM supported")
            data = f.read(int(w) * int(h) * 3)
        return int(w), int(h), data

    @staticmethod
    def write_ppm(path: Union[str, Path], width: int, height: int, data: BytesLike) -> None:
        b = _as_bytes(data)
        with open(path, "wb") as f:
            f.write(f"P6\n{int(width)} {int(height)}\n255\n".encode("ascii"))
            f.write(b)

    @classmethod
    def from_ppm(cls, path, **kwargs):
        w, h, data = cls.read_ppm(path)
        return cls(data, width=w, height=h, **kwargs)

    def to_ppm(self, path):
        self.write_ppm(path, self.width, self.height, self.run())

    def to_raw(self) -> bytearray:
        return bytearray(self.run())

    @classmethod
    def from_raw(cls, data, width, height, **kwargs):
        return cls(data, width=width, height=height, **kwargs)

    @classmethod
    def render_file(cls, input_path: Union[str, Path], output_path: Union[str, Path], recipe: Optional[Recipe] = None, **kwargs) -> bytes:
        w, h, data = cls.read_ppm(input_path)
        if recipe is not None:
            kwargs["recipe"] = recipe
            if "simulation" not in kwargs:
                kwargs["simulation"] = recipe.film_simulation
        runner = cls(data, width=w, height=h, **kwargs)
        out = runner.run()
        cls.write_ppm(output_path, w, h, out)
        return out

    # ---------- stages ----------
    def apply_white_balance(self, data: BytesLike) -> bytes:
        b = _as_bytes(data)
        if self.wb_shift_r == 0 and self.wb_shift_b == 0:
            return b
        out = bytearray()
        sr = self.wb_shift_r * 4
        sb = self.wb_shift_b * 4
        for i in range(0, len(b), 3):
            r = min(255, max(0, b[i] + sr))
            g = b[i + 1]
            bb = min(255, max(0, b[i + 2] + sb))
            out.extend((r, g, bb))
        return bytes(out)

    def apply_color_matrix(self, data: BytesLike) -> bytes:
        b = _as_bytes(data)
        M = _matrix_for(self.simulation)
        out = bytearray()
        for i in range(0, len(b), 3):
            r = b[i] / 255.0
            g = b[i + 1] / 255.0
            bb = b[i + 2] / 255.0
            nr = M[0] * r + M[1] * g + M[2] * bb
            ng = M[3] * r + M[4] * g + M[5] * bb
            nb = M[6] * r + M[7] * g + M[8] * bb
            out.extend((_clamp(nr * 255.0), _clamp(ng * 255.0), _clamp(nb * 255.0)))
        return bytes(out)

    def apply_color_chrome(self, data: BytesLike) -> bytes:
        proc = ColorChromeProcessor(chrome_level=self.chrome_level, chrome_blue_level=self.chrome_blue_level)
        return proc.process_image(data, self.width, self.height)

    def apply_clarity(self, data: BytesLike) -> bytes:
        if self.clarity == 0:
            return _as_bytes(data)
        b = _as_bytes(data)
        # luma plane
        luma = bytearray()
        for i in range(0, len(b), 3):
            L = 0.299 * b[i] + 0.587 * b[i + 1] + 0.114 * b[i + 2]
            luma.append(int(round(L)))
        filt = ClarityFilter(clarity_level=self.clarity)
        new_luma = filt.apply(bytes(luma), self.width, self.height)
        out = bytearray()
        for i in range(0, len(b), 3):
            idx = i // 3
            old = luma[idx]
            nl = new_luma[idx]
            factor = (nl / old) if old > 1e-6 else 1.0
            out.append(_clamp(b[i] * factor))
            out.append(_clamp(b[i + 1] * factor))
            out.append(_clamp(b[i + 2] * factor))
        return bytes(out)

    def _tone_lut(self) -> List[int]:
        if self.highlight == 0 and self.shadow == 0:
            return list(range(256))
        lut = [0] * 256
        hl = self.highlight  # -2..4
        sh = self.shadow
        for i in range(256):
            x = i / 255.0
            # shadow: lift/crush lows; highlight: lift/crush highs
            y = x
            # shadow influence stronger in lows
            y += (sh / 10.0) * (1.0 - x) * (1.0 - x)
            # highlight influence stronger in highs
            y += (hl / 10.0) * x * x
            y = max(0.0, min(1.0, y))
            lut[i] = int(round(y * 255.0))
        return lut

    def apply_tone_curve(self, data: BytesLike) -> bytes:
        if self.highlight == 0 and self.shadow == 0:
            return _as_bytes(data)
        b = _as_bytes(data)
        lut = self._tone_lut()
        out = bytearray()
        for v in b:
            out.append(lut[v])
        return bytes(out)

    def apply_grain(self, data: BytesLike) -> bytes:
        if not self.grain or str(self.grain).upper() in ("OFF", "NONE", "0"):
            return _as_bytes(data)
        buf = bytearray(_as_bytes(data))
        strength = self.grain
        try:
            strength = GrainRoughness(strength)
        except Exception:
            strength = GrainRoughness.WEAK if str(strength).lower() not in ("off", "none", "0", "") else GrainRoughness.OFF
        size = self.grain_size
        try:
            size = GrainSize(size)
        except Exception:
            size = GrainSize.SMALL
        cfg = GrainConfig(strength=strength, size=size, seed=self.seed)
        synth = GrainSynthesizer(cfg)
        synth.apply_to_buffer(buf, self.width, self.height, fmt="rgb")
        return bytes(buf)

    def run(self) -> bytes:
        data = self.image
        data = self.apply_white_balance(data)
        data = self.apply_color_matrix(data)
        data = self.apply_color_chrome(data)
        data = self.apply_clarity(data)
        data = self.apply_tone_curve(data)
        data = self.apply_grain(data)
        return data

    # aliases
    render = run
    process = run
    execute = run

    # convenience
    def __call__(self):
        return self.run()
