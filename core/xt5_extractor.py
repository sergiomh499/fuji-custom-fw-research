"""Fujifilm X-T5 firmware extractor (v4.31, X-Trans V HR / X-Processor 5).

Inspects an *unpacked* X-T5 firmware binary for:
  * Nostalgic Neg / Eterna Bleach Bypass / Reala ACE (and other) film
    simulation descriptors and 3x3 color transform matrices (Q12 or Q15
    fixed point, scale 4096 / 32768),
  * tone curves,
  * 40.2MP X-Trans V HR sensor resolution parameters,
  * X-Processor 5 architecture headers.

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

# Film-simulation tokens present on X-Processor 5.
XT5_FILM_TOKENS: Dict[str, str] = {
    # New on X-T5 / X-Processor 5
    "NOSTALGIC_NEG": "Nostalgic Neg",
    "NEG_N": "Nostalgic Neg",
    "NOSTALGIC": "Nostalgic Neg",
    "BLEACH_BYPASS": "Eterna Bleach Bypass",
    "ETERNA_BB": "Eterna Bleach Bypass",
    "BYPASS": "Eterna Bleach Bypass",
    "REALA": "Reala ACE",
    "REALA_ACE": "Reala ACE",
    # Carried over
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
    "MONO": "Monochrome",
    "SEP": "Sepia",
    "SEPIA": "Sepia",
    "ACROS": "Acros",
    "ACROS_YE": "Acros+Ye",
    "ACROS_R": "Acros+R",
    "ACROS_G": "Acros+G",
}

TOKENS = XT5_FILM_TOKENS

MATRIX_LEN = 9
DEFAULT_SCALE_Q12 = 4096
DEFAULT_SCALE_Q15 = 32768
DEFAULT_SCALE = DEFAULT_SCALE_Q12

SENSOR_RESOLUTION_MARKERS = (
    b"40.2MP",
    b"40.2 MP",
    b"7728",
    b"5152",
    b"X-TRANS V",
    b"XTRANSV",
    b"XTRANS V",
)

PROCESSOR_MARKERS = (
    b"X-Processor 5",
    b"X-Processor5",
    b"XPROCESSOR5",
    b"XPROC5",
    b"X-PROCESSOR 5",
)

COLOR_CHROME_MARKERS = (
    b"COLOR_CHROME",
    b"CHROME_EFFECT",
    b"FX_BLUE",
    b"C_CHROM",
    b"CHROM",
)


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


def _range_or_default(search_range, data_len: int = 0):
    if search_range is None:
        return (0, data_len if data_len else None)
    return tuple(search_range)


class XT5Extractor:
    """Inspect an unpacked Fujifilm X-T5 firmware binary."""

    MITIGATION_LINKS = {"firmware": MITIGATION_FIRMWARE, "ptp": MITIGATION_PTP}
    TOKENS = XT5_FILM_TOKENS
    XT5_FILM_TOKENS = XT5_FILM_TOKENS
    MATRIX_LEN = MATRIX_LEN
    DEFAULT_SCALE = DEFAULT_SCALE
    DEFAULT_SCALE_Q12 = DEFAULT_SCALE_Q12
    DEFAULT_SCALE_Q15 = DEFAULT_SCALE_Q15

    def __init__(self, data: BytesLike = b"", path=None, search_range=None, **kwargs):
        if isinstance(data, (tuple, list)):
            search_range = data
            data = path if path is not None else b""
            path = None
        if isinstance(path, (tuple, list)):
            search_range = path
            path = None
        if data in (b"", None) and path is not None:
            data = path
            path = None
        if isinstance(data, (str, Path)) and path is None:
            try:
                Path(data).read_bytes()
                path = data
                data = b""
            except Exception:
                pass
        if data in (b"", None) and path is not None:
            data = path
            path = None
        if "search_range" in kwargs:
            search_range = kwargs["search_range"]
        self.data = _as_bytes(data)
        if search_range is None:
            search_range = (0, len(self.data))
        self.search_range = tuple(search_range)
        self.header = self.parse_header()
        self.film_tokens = self.find_film_tokens()
        self.nostalgic_negative = self.find_nostalgic_negative()
        self.bleach_bypass = self.find_bleach_bypass()
        self.reala = self.find_reala()
        self.classic_negative = self.find_classic_negative()
        self.eterna = self.find_eterna()
        self.color_chrome = self.find_color_chrome()
        self.matrices = self.extract_matrices()
        self.tone_curves = self.extract_tone_curves()
        self.sensor_resolution = self.find_sensor_resolution()
        self.architecture_header = self.find_architecture_header()

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

    parse_xt5_header = parse_header
    get_header = parse_header
    parse_xt_header = parse_header

    # ---------------------------------------------------------------- tokens
    def find_film_tokens(self, search_range=None) -> List[Dict[str, Any]]:
        sr = self._sr(search_range)
        start = sr[0] if sr[0] is not None else 0
        end = sr[1] if (sr[1] is not None) else len(self.data)
        b = self.data
        results: List[dict] = []
        for token, name in sorted(XT5_FILM_TOKENS.items(), key=lambda kv: -len(kv[0])):
            needle = token.encode("ascii")
            pos = b.find(needle, start)
            while pos != -1 and pos < end:
                results.append({"token": token, "name": name, "offset": pos})
                pos = b.find(needle, pos + 1)
                if pos == -1 or pos >= end:
                    break
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
        return _range_or_default(search_range, len(self.data))

    # ---------------------------------------------------------------- convenience film groups
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

    def find_nostalgic_negative(self, search_range=None):
        return self._find_by_tokens(search_range, {"NOSTALGIC_NEG", "NEG_N", "NOSTALGIC"})

    scan_nostalgic_negative = find_nostalgic_negative
    extract_nostalgic_negative = find_nostalgic_negative

    def find_bleach_bypass(self, search_range=None):
        return self._find_by_tokens(search_range, {"BLEACH_BYPASS", "ETERNA_BB", "BYPASS"})

    scan_bleach_bypass = find_bleach_bypass
    extract_bleach_bypass = find_bleach_bypass

    def find_reala(self, search_range=None):
        return self._find_by_tokens(search_range, {"REALA", "REALA_ACE"})

    scan_reala = find_reala
    extract_reala = find_reala
    find_reala_ace = find_reala
    extract_reala_ace = find_reala

    def find_classic_negative(self, search_range=None):
        return self._find_by_tokens(search_range, {"CLASSIC_NEG", "NEG_C"})

    scan_classic_negative = find_classic_negative
    extract_classic_negative = find_classic_negative

    def find_eterna(self, search_range=None):
        return self._find_by_tokens(search_range, {"ETERNA", "CINEMA", "BLEACH_BYPASS", "ETERNA_BB"})

    scan_eterna = find_eterna
    extract_eterna = find_eterna

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
                vals_int = []
                vals_float = []
                base = pos + len(marker)
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

    @classmethod
    def _read_matrix(cls, data: bytes, offset: int, dtype: str = "i", count: int = MATRIX_LEN):
        size = 4 * count
        if offset + size > len(data):
            return None
        if dtype.startswith("f"):
            fmt = "<" + "f" * count
        else:
            fmt = "<" + "i" * count
        try:
            vals = list(struct.unpack(fmt, data[offset:offset + size]))
        except struct.error:
            return None
        if dtype.startswith("i") and all(v == 0 for v in vals):
            return None
        return vals

    def extract_descriptors(self, data=None, search_range=None, dtype: str = "i",
                            scale: int = DEFAULT_SCALE, matrix_offset_delta: int = 0,
                            q: Optional[int] = None, **kwargs):
        if data is None:
            data = self.data
        b = _as_bytes(data)
        sr = self._sr(search_range) if search_range is not None else self.search_range
        start, end = sr
        if end is None:
            end = len(b)
        if q is not None:
            scale = DEFAULT_SCALE_Q15 if q == 15 else (DEFAULT_SCALE_Q12 if q == 12 else scale)
        tokens = self.find_film_tokens((start, end))
        # find_film_tokens operates on self.data; recompute on b
        # Recompute tokens directly on b for correctness
        toks = []
        for token, name in sorted(XT5_FILM_TOKENS.items(), key=lambda kv: -len(kv[0])):
            needle = token.encode("ascii")
            pos = b.find(needle, start)
            while pos != -1 and pos < end:
                toks.append({"token": token, "name": name, "offset": pos})
                pos = b.find(needle, pos + 1)
                if pos == -1 or pos >= end:
                    break
        by_offset: Dict[int, dict] = {}
        for r in toks:
            off = r["offset"]
            if off not in by_offset or len(r["token"]) > len(by_offset[off]["token"]):
                by_offset[off] = r
        tokens = sorted(by_offset.values(), key=lambda r: r["offset"])

        out: List[Dict[str, Any]] = []
        for t in tokens:
            mo = self._matrix_offset_after(b, t["offset"], t["token"]) + matrix_offset_delta
            matrix = self._read_matrix(b, mo, dtype=dtype)
            desc = {
                "token": t["token"],
                "name": t["name"],
                "offset": t["offset"],
                "matrix_offset": mo,
                "tone_lut_offset": (mo + MATRIX_LEN * 4) if matrix is not None else None,
                "dtype": dtype,
                "scale": scale,
                "q": 15 if scale == DEFAULT_SCALE_Q15 else 12,
                "mitigation": MITIGATION_FIRMWARE,
            }
            if matrix is not None:
                desc["matrix"] = matrix
                desc["matrix_float"] = [v / scale for v in matrix] if dtype.startswith("i") else list(matrix)
            else:
                desc["matrix"] = None
                desc["matrix_float"] = None
            out.append(desc)
        return out

    # aliases
    extract = extract_descriptors
    extract_all = extract_descriptors
    extract_simulations = extract_descriptors
    get_descriptors = extract_descriptors
    descriptors = lambda self, *a, **k: self.extract_descriptors(*a, **k)

    def extract_matrices(self, data=None, search_range=None, dtype: str = "i",
                         scale: int = DEFAULT_SCALE, **kwargs):
        descs = self.extract_descriptors(data=data, search_range=search_range, dtype=dtype, scale=scale, **kwargs)
        out: Dict[str, List] = {}
        for d in descs:
            if d.get("matrix") is not None:
                out[d["token"]] = d["matrix"]
        return out

    get_matrices = extract_matrices
    matrices = extract_matrices

    def extract_tone_curves(self, data=None, search_range=None, dtype: str = "i",
                            count: int = 4, **kwargs):
        descs = self.extract_descriptors(data=data, search_range=search_range, dtype=dtype, **kwargs)
        b = self.data if data is None else _as_bytes(data)
        sr = self._sr(search_range) if search_range is not None else self.search_range
        start, end = sr
        if end is None:
            end = len(b)
        out: List[dict] = []
        for d in descs:
            off = d.get("tone_lut_offset")
            if off is None:
                continue
            try:
                size = 4 * count
                if off + size > len(b):
                    continue
                if dtype.startswith("f"):
                    fmt = "<" + "f" * count
                else:
                    fmt = "<" + "i" * count
                vals = list(struct.unpack(fmt, b[off:off + size]))
            except Exception:
                vals = None
            out.append({"token": d["token"], "offset": off, "values": vals})
        return out

    # ---------------------------------------------------------------- sensor resolution
    def find_sensor_resolution(self, search_range=None):
        return self._scan_markers(search_range, SENSOR_RESOLUTION_MARKERS, "sensor_resolution")

    scan_sensor_resolution = find_sensor_resolution
    extract_sensor_resolution = find_sensor_resolution
    find_sensor_parameters = find_sensor_resolution
    scan_sensor_parameters = find_sensor_resolution
    get_sensor_resolution = find_sensor_resolution

    # ---------------------------------------------------------------- architecture header
    def find_architecture_header(self, search_range=None):
        return self._scan_markers(search_range, PROCESSOR_MARKERS, "architecture_header")

    find_processor_header = find_architecture_header
    scan_architecture_header = find_architecture_header
    parse_architecture_header = find_architecture_header
    find_xprocessor5 = find_architecture_header
    find_x_processor_5 = find_architecture_header
    scan_processor_header = find_architecture_header

    def _scan_markers(self, search_range, markers, kind):
        sr = self._sr(search_range)
        start = sr[0] if sr[0] is not None else 0
        end = sr[1] if (sr[1] is not None) else len(self.data)
        low = self.data.lower()
        results = []
        for marker in markers:
            pos = low.find(marker.lower(), start)
            while pos != -1 and pos < end:
                # read a couple of following u32 as parameters if present
                params = []
                base = pos + len(marker)
                if base % 4:
                    base += 4 - (base % 4)
                for j in range(4):
                    off = base + j * 4
                    if off + 4 <= len(self.data):
                        params.append(_u32(self.data, off))
                results.append({
                    "kind": kind,
                    "marker": marker.decode("latin1", "replace"),
                    "offset": pos,
                    "parameters": params,
                    "mitigation": MITIGATION_FIRMWARE,
                })
                pos = low.find(marker.lower(), pos + 1)
                if pos == -1 or pos >= end:
                    break
        # de-dup by offset
        uniq = []
        seen = set()
        for r in results:
            if r["offset"] in seen:
                continue
            seen.add(r["offset"])
            uniq.append(r)
        return uniq

    # ---------------------------------------------------------------- analyze
    def analyze(self) -> Dict[str, Any]:
        return {
            "header": self.header,
            "film_tokens": self.film_tokens,
            "nostalgic_negative": self.nostalgic_negative,
            "bleach_bypass": self.bleach_bypass,
            "reala": self.reala,
            "classic_negative": self.classic_negative,
            "eterna": self.eterna,
            "color_chrome": self.color_chrome,
            "matrices": self.matrices,
            "tone_curves": self.tone_curves,
            "sensor_resolution": self.sensor_resolution,
            "architecture_header": self.architecture_header,
            "mitigations": {
                "firmware": MITIGATION_FIRMWARE,
                "ptp": MITIGATION_PTP,
            },
        }

    run = analyze
    scan = analyze
    to_dict = analyze


# Module-level helpers
def analyze_xt5(data: BytesLike) -> Dict[str, Any]:
    return XT5Extractor(data).analyze()


def parse_header(data: BytesLike) -> Optional[Dict[str, Any]]:
    return XT5Extractor(data).parse_header()


def find_film_tokens(data: BytesLike, search_range=None):
    return XT5Extractor(data).find_film_tokens(search_range)


def find_nostalgic_negative(data: BytesLike, search_range=None):
    return XT5Extractor(data).find_nostalgic_negative(search_range)


def find_bleach_bypass(data: BytesLike, search_range=None):
    return XT5Extractor(data).find_bleach_bypass(search_range)


def find_reala(data: BytesLike, search_range=None):
    return XT5Extractor(data).find_reala(search_range)


def extract_matrices(data: BytesLike, search_range=None, dtype: str = "i", scale: int = DEFAULT_SCALE):
    return XT5Extractor(data).extract_matrices(search_range=search_range, dtype=dtype, scale=scale)


def extract_tone_curves(data: BytesLike, search_range=None, dtype: str = "i", count: int = 4):
    return XT5Extractor(data).extract_tone_curves(search_range=search_range, dtype=dtype, count=count)


def find_sensor_resolution(data: BytesLike, search_range=None):
    return XT5Extractor(data).find_sensor_resolution(search_range)


def find_architecture_header(data: BytesLike, search_range=None):
    return XT5Extractor(data).find_architecture_header(search_range)
