"""Fujifilm X-T30 firmware extractor (v2.01, X-Trans IV / X-Processor 4).

Inspects an *unpacked* X-T30 firmware binary for:
  * Classic Negative / Eterna / Cinema film simulation descriptors and
    3x3 color transform matrices (Q12 fixed point, scale 4096),
  * Color Chrome Effect / Color Chrome FX Blue descriptors and saturation
    compression threshold constants.

Failure mitigation:
- Volatile / PTP RAM recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
- Firmware repacking / patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

BytesLike = Union[bytes, bytearray, memoryview, str, Path]

MITIGATION_FIRMWARE = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery"
MITIGATION_PTP = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery"

# Film-simulation tokens introduced / present on X-Processor 4.
XT30_FILM_TOKENS: Dict[str, str] = {
    "CLASSIC_NEG": "Classic Negative",
    "NEG_C": "Classic Negative",
    "NEG_H": "Pro Neg. Hi",
    "NEG_S": "Pro Neg. Std",
    "ETERNA": "Eterna",
    "CINEMA": "Eterna Cinema",
    "PROV": "Provia",
    "PROVIA": "Provia",
    "VEL": "Velvia",
    "VELV": "Velvia",
    "_ASTIA": "Astia",
    "ASTIA": "Astia",
    "CHROME": "Classic Chrome",
    "CLASSIC": "Classic Chrome",
    "BW_": "Monochrome",
    "BW": "Monochrome",
    "SEP": "Sepia",
    "SEPIA": "Sepia",
    "ACROS": "Acros",
}

# Color Chrome related menu / DSP descriptors.
COLOR_CHROME_MARKERS = (
    b"COLOR_CHROME",
    b"CHROME_EFFECT",
    b"FX_BLUE",
    b"C_CHROM",
    b"CHROM",
)

_COLOR_MATRIX_MARKERS = (
    b"CLASSIC_NEG",
    b"NEG_C",
    b"ETERNA",
    b"CINEMA",
    b"COLOR_MATRIX",
    b"COLORMATRIX",
    b"SENSOR_MATRIX",
)

MATRIX_LEN = 9
DEFAULT_SCALE = 4096


def _as_bytes(data: Any) -> bytes:
    if data is None:
        return b""
    if isinstance(data, (str, Path)):
        return Path(data).read_bytes()
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    if hasattr(data, "data"):
        return bytes(data.data)
    if hasattr(data, "raw"):
        return bytes(data.raw)
    return bytes(data)


def _u32(data: bytes, off: int) -> int:
    if off + 4 > len(data):
        return 0
    return struct.unpack_from("<I", data, off)[0]


def _range_or_default(search_range):
    if search_range is None:
        return (0, None)
    return tuple(search_range)


class XT30Extractor:
    """Inspect an unpacked Fujifilm X-T30 firmware binary."""

    TOKENS = XT30_FILM_TOKENS
    COLOR_CHROME_MARKERS = COLOR_CHROME_MARKERS
    MATRIX_LEN = MATRIX_LEN
    DEFAULT_SCALE = DEFAULT_SCALE
    MITIGATION_LINKS = {
        "firmware": MITIGATION_FIRMWARE,
        "ptp": MITIGATION_PTP,
    }

    def __init__(self, data: BytesLike = b"", path: Optional[Union[str, Path]] = None,
                 search_range=None):
        if data in (b"", None) and path is not None:
            data = path
        # Allow XT30Extractor(path_string)
        if isinstance(data, (str, Path)) and path is None:
            try:
                Path(data).read_bytes()
                path = data
                data = b""
            except Exception:
                pass
        if data in (b"", None) and path is not None:
            data = path
        self.data = _as_bytes(data)
        self.search_range = _range_or_default(search_range)
        self.header = self.parse_header()
        self.film_tokens = self.find_film_tokens()
        self.classic_negative = self.find_classic_negative()
        self.eterna = self.find_eterna()
        self.color_chrome = self.find_color_chrome()
        self.matrices = self.extract_matrices()

    # ---------------------------------------------------------------- header
    def parse_header(self) -> Optional[Dict[str, Any]]:
        if len(self.data) < 20:
            return None
        try:
            from core.container import FujiContainer

            fw = FujiContainer(self.data[:532] if len(self.data) >= 532 else self.data)
            meta = fw.to_metadata()
            return {
                "os_type": meta.get("os_type"),
                "model_code": meta.get("model_code"),
                "v1": meta.get("v1"),
                "v2": meta.get("v2"),
                "version": meta.get("version"),
                "checksum": meta.get("checksum"),
                "header_size": meta.get("header_size"),
                "payload_size": meta.get("payload_size"),
                "mitigation": MITIGATION_FIRMWARE,
            }
        except Exception:
            return None

    get_header = parse_header
    parse_xt30_header = parse_header

    # ---------------------------------------------------------------- tokens
    def find_film_tokens(self, search_range=None) -> List[Dict[str, Any]]:
        sr = self._sr(search_range)
        start = sr[0] if sr[0] is not None else 0
        end = sr[1] if (sr[1] is not None) else len(self.data)
        results: List[dict] = []
        for token, name in sorted(XT30_FILM_TOKENS.items(), key=lambda kv: -len(kv[0])):
            needle = token.encode("ascii")
            pos = self.data.find(needle, start)
            while pos != -1 and pos < end:
                results.append({"token": token, "name": name, "offset": pos})
                pos = self.data.find(needle, pos + 1)
                if pos == -1 or pos >= end:
                    break
        # de-dup by offset keeping longest token
        by_offset: Dict[int, dict] = {}
        for r in results:
            off = r["offset"]
            if off not in by_offset or len(r["token"]) > len(by_offset[off]["token"]):
                by_offset[off] = r
        return sorted(by_offset.values(), key=lambda r: r["offset"])

    # aliases
    parse_tokens = find_film_tokens
    scan_tokens = find_film_tokens
    get_tokens = find_film_tokens
    find_tokens = find_film_tokens

    def _sr(self, search_range):
        if search_range is None:
            return self.search_range
        return _range_or_default(search_range)

    # ---------------------------------------------------------------- classic negative
    def find_classic_negative(self, search_range=None) -> List[Dict[str, Any]]:
        return self._find_by_tokens(search_range, {"CLASSIC_NEG", "NEG_C", "NEG_H"})

    scan_classic_negative = find_classic_negative
    extract_classic_negative = find_classic_negative

    def find_eterna(self, search_range=None) -> List[Dict[str, Any]]:
        return self._find_by_tokens(search_range, {"ETERNA", "CINEMA"})

    scan_eterna = find_eterna
    extract_eterna = find_eterna

    def _find_by_tokens(self, search_range, token_set) -> List[Dict[str, Any]]:
        toks = [t for t in self.find_film_tokens(search_range) if t["token"] in token_set]
        out: List[Dict[str, Any]] = []
        for t in toks:
            mo = self._matrix_offset_after(self.data, t["offset"], t["token"])
            matrix = self._read_matrix(self.data, mo)
            desc = {
                "token": t["token"],
                "name": t["name"],
                "offset": t["offset"],
                "matrix_offset": mo,
                "tone_lut_offset": (mo + MATRIX_LEN * 4) if matrix is not None else None,
                "matrix": matrix,
                "matrix_float": [v / DEFAULT_SCALE for v in matrix] if matrix is not None else None,
                "scale": DEFAULT_SCALE,
                "mitigation": MITIGATION_FIRMWARE,
            }
            out.append(desc)
        return out

    # ---------------------------------------------------------------- color chrome
    def find_color_chrome(self, search_range=None) -> List[Dict[str, Any]]:
        sr = self._sr(search_range)
        start = sr[0] if sr[0] is not None else 0
        end = sr[1] if (sr[1] is not None) else len(self.data)
        results: List[Dict[str, Any]] = []
        low = self.data.lower()
        for marker in COLOR_CHROME_MARKERS:
            pos = low.find(marker.lower(), start)
            while pos != -1 and pos < end:
                # read following 4 float32 constants (thresholds/factors) if present
                vals_int = []
                vals_float = []
                base = pos + len(marker)
                # align to 4
                if base % 4:
                    base += 4 - (base % 4)
                for j in range(4):
                    off = base + j * 4
                    if off + 4 <= len(self.data):
                        vals_int.append(struct.unpack_from("<i", self.data, off)[0])
                        vals_float.append(struct.unpack_from("<f", self.data, off)[0])
                results.append({
                    "marker": marker.decode("latin1"),
                    "offset": pos,
                    "constants_offset": base,
                    "constants_int": vals_int,
                    "constants_float": vals_float,
                    "mitigation": MITIGATION_FIRMWARE,
                })
                pos = low.find(marker.lower(), pos + 1)
                if pos == -1 or pos >= end:
                    break
        # de-dup by offset
        uniq: List[Dict[str, Any]] = []
        seen = set()
        for r in results:
            if r["offset"] in seen:
                continue
            seen.add(r["offset"])
            uniq.append(r)
        return uniq

    scan_color_chrome = find_color_chrome
    extract_color_chrome = find_color_chrome

    # ---------------------------------------------------------------- matrices
    @staticmethod
    def _matrix_offset_after(data: bytes, token_offset: int, token: str) -> int:
        mo = token_offset + len(token)
        while mo + 4 <= len(data) and data[mo:mo + 4] == b"\x00\x00\x00\x00":
            mo += 4
        return mo

    @staticmethod
    def _read_matrix(data: bytes, offset: int, count: int = MATRIX_LEN):
        size = 4 * count
        if offset + size > len(data):
            return None
        try:
            vals = list(struct.unpack("<" + "i" * count, data[offset:offset + size]))
        except struct.error:
            return None
        if all(v == 0 for v in vals):
            return None
        return vals

    def extract_descriptors(self, search_range=None, dtype: str = "i", scale: int = DEFAULT_SCALE,
                            matrix_offset_delta: int = 0) -> List[Dict[str, Any]]:
        sr = self._sr(search_range)
        start = sr[0] if sr[0] is not None else 0
        end = sr[1] if (sr[1] is not None) else len(self.data)
        tokens = self.find_film_tokens((start, end))
        out: List[Dict[str, Any]] = []
        for t in tokens:
            mo = self._matrix_offset_after(self.data, t["offset"], t["token"]) + matrix_offset_delta
            matrix = self._read_matrix(self.data, mo) if dtype.startswith("i") else None
            if dtype.startswith("f"):
                try:
                    matrix = list(struct.unpack("<" + "f" * MATRIX_LEN, self.data[mo:mo + MATRIX_LEN * 4]))
                except struct.error:
                    matrix = None
            desc = {
                "token": t["token"],
                "name": t["name"],
                "offset": t["offset"],
                "matrix_offset": mo,
                "tone_lut_offset": (mo + MATRIX_LEN * 4) if matrix is not None else None,
                "dtype": dtype,
                "scale": scale,
                "matrix": matrix,
                "matrix_float": [v / scale for v in matrix] if (matrix is not None and dtype.startswith("i")) else (list(matrix) if matrix is not None else None),
                "mitigation": MITIGATION_FIRMWARE,
            }
            out.append(desc)
        return out

    extract = extract_descriptors
    extract_all = extract_descriptors
    extract_simulations = extract_descriptors
    get_descriptors = extract_descriptors
    descriptors = lambda self, *a, **k: self.extract_descriptors(*a, **k)

    def extract_matrices(self, search_range=None, dtype: str = "i", scale: int = DEFAULT_SCALE) -> Dict[str, List]:
        descs = self.extract_descriptors(search_range=search_range, dtype=dtype, scale=scale)
        out: Dict[str, List] = {}
        for d in descs:
            if d.get("matrix") is not None:
                out[d["token"]] = d["matrix"]
        return out

    get_matrices = extract_matrices
    matrices = extract_matrices

    # ---------------------------------------------------------------- analyze
    def analyze(self) -> Dict[str, Any]:
        return {
            "header": self.header,
            "film_tokens": self.film_tokens,
            "classic_negative": self.classic_negative,
            "eterna": self.eterna,
            "color_chrome": self.color_chrome,
            "matrices": self.matrices,
            "mitigations": {
                "firmware": MITIGATION_FIRMWARE,
                "ptp": MITIGATION_PTP,
            },
        }

    run = analyze
    scan = analyze
    to_dict = analyze

    # color chrome threshold constants (software defaults + extracted)
    @property
    def color_chrome_thresholds(self) -> Dict[str, Any]:
        return {
            "saturation_threshold": 0.25,
            "warm_hue_ranges": [(0.0, 120.0), (300.0, 360.0)],
            "blue_hue_range": (180.0, 250.0),
            "chrome_factors": {"weak": 0.12, "strong": 0.28},
            "blue_factors": {"weak": 0.10, "strong": 0.22},
        }


# Module-level helpers
def analyze_xt30(data: BytesLike) -> Dict[str, Any]:
    return XT30Extractor(data).analyze()


def parse_header(data: BytesLike) -> Optional[Dict[str, Any]]:
    return XT30Extractor(data).parse_header()


def find_film_tokens(data: BytesLike, search_range=None):
    return XT30Extractor(data).find_film_tokens(search_range)


def find_classic_negative(data: BytesLike, search_range=None):
    return XT30Extractor(data).find_classic_negative(search_range)


def find_eterna(data: BytesLike, search_range=None):
    return XT30Extractor(data).find_eterna(search_range)


def find_color_chrome(data: BytesLike, search_range=None):
    return XT30Extractor(data).find_color_chrome(search_range)


def extract_matrices(data: BytesLike, search_range=None, dtype: str = "i", scale: int = DEFAULT_SCALE):
    return XT30Extractor(data).extract_matrices(search_range=search_range, dtype=dtype, scale=scale)
