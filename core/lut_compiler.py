"""LUT compiler: convert .cube 3D-LUTs into Fujifilm DSP matrices.

Mitigation (firmware repacking/patching): docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
Mitigation (volatile/PTP memory): docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
Mitigation (hardware flashing): docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery

Numerical instability during least-squares fitting falls back to the identity
matrix (Q15, scale 32768) instead of emitting a corrupt transform.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

MITIGATION_FIRMWARE = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery"
MITIGATION_PTP = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery"
MITIGATION_HARDWARE = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery"

Q15_SCALE = 32768
Q15_MIN = -32768
Q15_MAX = 32767


class LUTCompilerError(Exception):
    def __init__(self, message: str):
        super().__init__(f"{message} | mitigation: {MITIGATION_FIRMWARE}")


class NumericalInstabilityError(LUTCompilerError):
    pass


def _as_text(source: Any) -> str:
    if source is None:
        return ""
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source).decode("utf-8", errors="replace")
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8", errors="replace")
    s = str(source)
    p = Path(s)
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    return s


class CubeLUTParser:
    """Parse a .cube 3D-LUT file.

    On parse failure raises LUTCompilerError (mitigation: firmware-level-recovery).
    """

    def __init__(self, source: Any = None):
        self.title: Optional[str] = None
        self.size: Optional[int] = None
        self.domain_min: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.domain_max: Tuple[float, float, float] = (1.0, 1.0, 1.0)
        self.entries: List[Tuple[float, float, float]] = []
        # aliases
        self.data = self.entries
        self.values = self.entries
        self.colors = self.entries
        self.rgb_data = self.entries
        self.lut_data = self.entries
        if source is not None:
            self.parse(source)

    @property
    def lut_size(self) -> Optional[int]:
        return self.size

    def parse(self, source: Any) -> "CubeLUTParser":
        text = _as_text(source)
        self.entries.clear()
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            low = line.lower()
            if low.startswith("title"):
                # TITLE "name" or TITLE name
                parts = line.split(None, 1)
                self.title = parts[1].strip().strip('"') if len(parts) > 1 else None
                continue
            if low.startswith("lut_3d_size"):
                self.size = int(line.split()[-1])
                continue
            if low.startswith("domain_min"):
                self.domain_min = tuple(float(x) for x in line.split()[1:4])  # type: ignore
                continue
            if low.startswith("domain_max"):
                self.domain_max = tuple(float(x) for x in line.split()[1:4])  # type: ignore
                continue
            if low.startswith("lut_1d_size") or low.startswith("lut_2d") or low.startswith("lut_3d"):
                continue
            # data line: 3 floats
            toks = line.split()
            if len(toks) >= 3:
                try:
                    r, g, b = float(toks[0]), float(toks[1]), float(toks[2])
                except ValueError:
                    continue
                self.entries.append((r, g, b))
        if self.size is None:
            # infer cube root
            n = round(len(self.entries) ** (1.0 / 3.0))
            if n * n * n == len(self.entries):
                self.size = n
        return self

    def parse_file(self, path: Any) -> "CubeLUTParser":
        return self.parse(path)

    def parse_text(self, text: str) -> "CubeLUTParser":
        return self.parse(text)

    def load(self, source: Any) -> "CubeLUTParser":
        return self.parse(source)

    # common aliases
    read = parse
    from_file = classmethod(lambda cls, p: cls(p))
    from_text = classmethod(lambda cls, t: cls(t))


def _identity_float() -> List[float]:
    return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]


def _identity_q15() -> List[int]:
    return [Q15_SCALE, 0, 0, 0, Q15_SCALE, 0, 0, 0, Q15_SCALE]


def _solve_3x3(a: List[List[float]], b: List[float]) -> Optional[List[float]]:
    # Gaussian elimination with partial pivot.
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    n = 3
    for col in range(n):
        # pivot
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-18:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        pv = m[col][col]
        for j in range(col, n + 1):
            m[col][j] /= pv
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col]
            if factor != 0.0:
                for j in range(col, n + 1):
                    m[r][j] -= factor * m[col][j]
    return [m[i][n] for i in range(n)]


def _fit_lstsq(inputs: List[List[float]], outputs: List[List[float]]) -> Optional[List[float]]:
    # inputs/outputs: list of (3,) ; solve M (3x3) minimizing ||M x - y||.
    # Build normal equations per output row.
    # X^T X (3x3)
    xtx = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    xty = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]  # [out_channel][coeff]
    for x, y in zip(inputs, outputs):
        for i in range(3):
            for j in range(3):
                xtx[i][j] += x[i] * x[j]
        for c in range(3):
            for i in range(3):
                xty[c][i] += x[i] * y[c]
    # solve for each output channel
    matrix = [0.0] * 9
    for c in range(3):
        sol = _solve_3x3([row[:] for row in xtx], [xty[c][i] for i in range(3)])
        if sol is None:
            return None
        for i in range(3):
            matrix[c * 3 + i] = sol[i]
    return matrix


class DSPMatrixOptimizer:
    """Fit a 3x3 color matrix (Q15) to a 3D-LUT."""

    MITIGATION = MITIGATION_FIRMWARE

    def __init__(self, cube: Any = None):
        self.matrix_float: List[float] = _identity_float()
        self.matrix: List[int] = _identity_q15()
        self.matrix_q15: List[int] = self.matrix
        self.coefficients: List[int] = self.matrix
        if cube is not None:
            self.fit(cube)

    def _entries_from(self, source: Any) -> Tuple[List, Optional[int]]:
        if isinstance(source, CubeLUTParser):
            return source.entries, source.size
        if isinstance(source, (list, tuple)):
            # could be entries or a matrix
            if len(source) > 0 and isinstance(source[0], (list, tuple)) and len(source[0]) == 3:
                return list(source), None
            return [], None
        # try parse
        try:
            p = CubeLUTParser(source)
            return p.entries, p.size
        except Exception:
            return [], None

    def fit(self, source: Any = None, cube: Any = None) -> List[int]:
        src = cube if cube is not None else source
        entries, size = self._entries_from(src)
        if not entries:
            # maybe source is already a matrix-like? fall back identity
            self.matrix_float = _identity_float()
            self.matrix = _identity_q15()
            self.matrix_q15 = self.matrix
            self.coefficients = self.matrix
            return list(self.matrix)
        n = size or round(len(entries) ** (1.0 / 3.0))
        if n < 1:
            n = 2
        # Build input grid coordinates (r outer, g mid, b inner) normalized.
        inputs: List[List[float]] = []
        outputs: List[List[float]] = []
        denom = max(1, n - 1)
        idx = 0
        for ri in range(n):
            for gi in range(n):
                for bi in range(n):
                    if idx >= len(entries):
                        break
                    r = ri / denom
                    g = gi / denom
                    b = bi / denom
                    o = entries[idx]
                    inputs.append([r, g, b])
                    outputs.append([float(o[0]), float(o[1]), float(o[2])])
                    idx += 1
        try:
            sol = _fit_lstsq(inputs, outputs)
            if sol is None:
                raise NumericalInstabilityError("singular normal equations")
            # sanity: finite
            if any(not math.isfinite(v) for v in sol):
                raise NumericalInstabilityError("non-finite solution")
            self.matrix_float = [float(v) for v in sol]
        except (NumericalInstabilityError, ZeroDivisionError, ValueError):
            # fall back to identity
            self.matrix_float = _identity_float()
        self.matrix = self.to_q15(self.matrix_float)
        self.matrix_q15 = self.matrix
        self.coefficients = self.matrix
        return list(self.matrix)

    # aliases
    fit_cube = fit
    fit_from_cube = fit
    optimize = fit
    fit_matrix = fit
    from_cube = fit

    @staticmethod
    def to_q15(matrix: Sequence[float], scale: int = Q15_SCALE) -> List[int]:
        out = []
        for v in matrix:
            q = int(round(float(v) * scale))
            if q < Q15_MIN:
                q = Q15_MIN
            if q > Q15_MAX:
                q = Q15_MAX
            out.append(q)
        # pad/truncate to 9
        while len(out) < 9:
            out.append(0)
        return out[:9]

    @staticmethod
    def to_float(matrix: Sequence[int], scale: int = Q15_SCALE) -> List[float]:
        return [float(v) / scale for v in matrix]

    @classmethod
    def from_matrix(cls, matrix):
        o = cls()
        if isinstance(matrix, (list, tuple)) and len(matrix) == 9 and all(isinstance(x, (int, float)) for x in matrix):
            # could be floats or q15; heuristic: values small -> floats
            if all(abs(x) <= 4.0 for x in matrix) and not all(isinstance(x, int) for x in matrix):
                o.matrix_float = [float(x) for x in matrix]
                o.matrix = o.to_q15(o.matrix_float)
            else:
                o.matrix = [int(x) for x in matrix]
                o.matrix_q15 = o.matrix
                o.matrix_float = o.to_float(o.matrix)
            o.coefficients = o.matrix
        return o

    @staticmethod
    def identity_q15() -> List[int]:
        return _identity_q15()

    @staticmethod
    def identity() -> List[int]:
        return _identity_q15()


class ToneCurveExtractor:
    """Extract a 1D neutral tone transfer curve from a 3D-LUT."""

    def __init__(self, cube: Any = None):
        self.curve: List[float] = []
        self.tone_curve = self.curve
        if cube is not None:
            self.extract(cube)

    def extract(self, source: Any = None, cube: Any = None) -> List[float]:
        src = cube if cube is not None else source
        entries: List = []
        size: Optional[int] = None
        if isinstance(src, CubeLUTParser):
            entries = src.entries
            size = src.size
        elif isinstance(src, DSPMatrixOptimizer):
            return list(self.curve)
        else:
            try:
                p = CubeLUTParser(src)
                entries = p.entries
                size = p.size
            except Exception:
                entries = []
        n = size or (round(len(entries) ** (1.0 / 3.0)) if entries else 0)
        if n < 1:
            self.curve = []
            self.tone_curve = self.curve
            return list(self.curve)
        denom = max(1, n - 1)
        out: List[float] = []
        for i in range(n):
            t = i / denom
            # neutral index: r=g=b=i -> position in r-outer/b-inner order
            # index = i*(n*n) + i*n + i
            idx = i * (n * n) + i * n + i
            if idx < len(entries):
                o = entries[idx]
                # luminance
                lum = 0.2126 * float(o[0]) + 0.7152 * float(o[1]) + 0.0722 * float(o[2])
                out.append(lum)
            else:
                out.append(t)
        self.curve = out
        self.tone_curve = self.curve
        return list(self.curve)

    # aliases
    extract_curve = extract
    extract_tone_curve = extract
    get_curve = extract
    get_tone_curve = extract


# Built-in presets (approximations)
def _preset_matrix(vals: Sequence[float]) -> List[int]:
    return DSPMatrixOptimizer.to_q15(list(vals))


PRESET_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "Classic Negative": {
        "matrix_float": [1.15, -0.10, -0.05, -0.05, 1.05, -0.05, -0.10, -0.05, 0.95],
        "tone_curve": [0.0, 0.05, 0.18, 0.35, 0.55, 0.75, 0.90, 0.97, 1.0],
    },
    "Eterna Bleach Bypass": {
        "matrix_float": [1.05, -0.25, -0.05, -0.10, 0.95, -0.05, -0.05, -0.15, 0.90],
        "tone_curve": [0.0, 0.08, 0.20, 0.38, 0.58, 0.76, 0.90, 0.97, 1.0],
    },
    "Nostalgic Neg": {
        "matrix_float": [1.10, 0.05, -0.05, -0.02, 1.02, 0.05, -0.08, 0.02, 0.90],
        "tone_curve": [0.0, 0.06, 0.19, 0.36, 0.56, 0.75, 0.89, 0.96, 1.0],
    },
}

PRESETS: Dict[str, List[int]] = {
    name: _preset_matrix(d["matrix_float"]) for name, d in PRESET_DEFINITIONS.items()
}
PRESET_MATRICES = PRESETS
BUILTIN_PRESETS = PRESETS
PRESET_TONE_CURVES = {name: d["tone_curve"] for name, d in PRESET_DEFINITIONS.items()}
PRESETS_FULL = {
    name: {
        "matrix": _preset_matrix(d["matrix_float"]),
        "matrix_float": list(d["matrix_float"]),
        "tone_curve": list(d["tone_curve"]),
    }
    for name, d in PRESET_DEFINITIONS.items()
}


def get_preset(name: str) -> Dict[str, Any]:
    if name not in PRESETS_FULL:
        raise LUTCompilerError(f"unknown preset: {name}")
    return PRESETS_FULL[name]


def list_presets() -> List[str]:
    return list(PRESET_DEFINITIONS.keys())


# Back-compat aliases
CubeParser = CubeLUTParser
LUTParser = CubeLUTParser
MatrixOptimizer = DSPMatrixOptimizer
ToneCurve = ToneCurveExtractor
