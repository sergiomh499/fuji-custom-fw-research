"""Film simulation descriptor extraction and matrix patching.

Reverse-engineered layout notes (X-T10 v1.31, unpacked binary):
  * Token table lives around 0x0024FB10 - 0x0024FB70.
  * Tokens are short ASCII names (PROV, VEL, _ASTIA, CHROME, NEG_H, BW_, SEP, ...)
    embedded in a compact serialized table.
  * Each simulation carries a 3x3 RGB->RGB color transform. Coefficients are
    stored as 32-bit little-endian fixed-point integers in Q12 (scale 4096)
    unless a caller overrides the dtype/scale. Tone curves follow the matrix as
    a 1-D LUT (offset = matrix_offset + 9*4).
"""

import struct
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

BytesLike = Union[bytes, bytearray, memoryview]

TOKENS: Dict[str, str] = {
    "PROV": "Provia",
    "VEL": "Velvia",
    "VELV": "Velvia",
    "_ASTIA": "Astia",
    "ASTIA": "Astia",
    "CHROME": "Classic Chrome",
    "NEG_H": "Pro Neg. Hi",
    "NEG_S": "Pro Neg. Std",
    "BW_": "Monochrome",
    "BW": "Monochrome",
    "SEPIA": "Sepia",
    "SEP": "Sepia",
    "ACROS": "Acros",
    "ETERNA": "Eterna",
    "CLASSIC": "Classic Chrome",
    "DYN": "Dynamic Range",
}

DEFAULT_RANGE: Tuple[int, int] = (0x0024FB10, 0x0024FB70)
MATRIX_LEN = 9
DEFAULT_SCALE = 4096  # Q12 fixed point


def _as_bytes(data: Any) -> bytes:
    if data is None:
        return b""
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    if hasattr(data, "data"):
        return bytes(data.data)
    return bytes(data)


def _range_or_default(search_range):
    if search_range is None:
        return DEFAULT_RANGE
    return tuple(search_range)


class FilmSimulationExtractor:
    """Inspect and parse film simulation descriptors / matrix tables."""

    TOKENS = TOKENS
    DEFAULT_RANGE = DEFAULT_RANGE
    MATRIX_LEN = MATRIX_LEN
    DEFAULT_SCALE = DEFAULT_SCALE

    def __init__(self, data: BytesLike = b"", search_range=None):
        self.data = _as_bytes(data)
        self.search_range = _range_or_default(search_range)

    # ------------------------------------------------------------------ tokens
    def parse_tokens(self_or_data=None, data=None, search_range=None):
        # support instance/class call styles
        if isinstance(self_or_data, FilmSimulationExtractor):
            inst = self_or_data
            if data is None:
                data = inst.data
            if search_range is None:
                search_range = inst.search_range
        elif isinstance(self_or_data, (bytes, bytearray, memoryview)) or hasattr(self_or_data, "data"):
            if data is None:
                data = self_or_data
        b = _as_bytes(data) if data is not None else b""
        sr = _range_or_default(search_range) if search_range is not None else DEFAULT_RANGE
        start, end = sr
        results: List[dict] = []
        # Build a stable token list ordered by length desc so longer tokens win.
        for token, name in sorted(TOKENS.items(), key=lambda kv: -len(kv[0])):
            needle = token.encode("ascii")
            pos = b.find(needle, start)
            while pos != -1 and pos < end:
                results.append({"token": token, "name": name, "offset": pos})
                pos = b.find(needle, pos + 1)
                if pos == -1 or pos >= end:
                    break
        # De-duplicate overlapping token hits (keep longest token at an offset).
        by_offset: Dict[int, dict] = {}
        for r in results:
            off = r["offset"]
            if off not in by_offset or len(r["token"]) > len(by_offset[off]["token"]):
                by_offset[off] = r
        out = sorted(by_offset.values(), key=lambda r: r["offset"])
        return out

    # alias names
    extract_tokens = parse_tokens
    get_tokens = parse_tokens
    find_tokens = parse_tokens

    # ------------------------------------------------------------- matrix read
    @staticmethod
    def _matrix_offset_after(data: bytes, token_offset: int, token: str) -> int:
        mo = token_offset + len(token)
        # skip full 32-bit zero words (padding), not single zero bytes
        while mo + 4 <= len(data) and data[mo:mo+4] == b"\x00\x00\x00\x00":
            mo += 4
        return mo

    @classmethod
    def _read_matrix(cls, data: bytes, offset: int, dtype: str = "i", count: int = MATRIX_LEN):
        size = 4 * count
        if offset + size > len(data):
            return None
        fmt = "<" + dtype[0] + str(count)  # 'i'/'f'
        # normalize dtype char
        if dtype.startswith("f"):
            fmt = "<" + "f" * count
        elif dtype.startswith("i"):
            fmt = "<" + "i" * count
        else:
            fmt = "<" + dtype[0] * count
        vals = list(struct.unpack(fmt, data[offset:offset + size]))
        return vals

    def extract_descriptors(self_or_data=None, data=None, search_range=None, dtype: str = "i",
                            scale: int = DEFAULT_SCALE, matrix_offset_delta: int = 0):
        if isinstance(self_or_data, FilmSimulationExtractor):
            inst = self_or_data
            if data is None:
                data = inst.data
            if search_range is None:
                search_range = inst.search_range
        elif isinstance(self_or_data, (bytes, bytearray, memoryview)) or hasattr(self_or_data, "data"):
            if data is None:
                data = self_or_data
        b = _as_bytes(data) if data is not None else b""
        sr = _range_or_default(search_range) if search_range is not None else DEFAULT_RANGE
        tokens = FilmSimulationExtractor.parse_tokens(None, b, sr)
        out: List[dict] = []
        for t in tokens:
            mo = FilmSimulationExtractor._matrix_offset_after(b, t["offset"], t["token"]) + matrix_offset_delta
            matrix = FilmSimulationExtractor._read_matrix(b, mo, dtype)
            desc = {
                "token": t["token"],
                "name": t["name"],
                "offset": t["offset"],
                "matrix_offset": mo,
                "tone_lut_offset": (mo + MATRIX_LEN * 4) if matrix is not None else None,
                "dtype": dtype,
                "scale": scale,
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

    def extract_matrices(self_or_data=None, data=None, search_range=None, dtype: str = "i",
                         scale: int = DEFAULT_SCALE):
        descs = FilmSimulationExtractor.extract_descriptors(self_or_data, data, search_range, dtype=dtype, scale=scale)
        out: Dict[str, List] = {}
        for d in descs:
            if d.get("matrix") is not None:
                out[d["token"]] = d["matrix"]
        return out

    get_matrices = extract_matrices
    matrices = extract_matrices

    def extract_instance(self, *a, **k):
        return self.extract_descriptors(self.data, self.search_range, *a, **k)

    # convenience instance wrappers
    def parse(self, *a, **k):
        return self.parse_tokens(self.data, self.search_range, *a, **k)

    def descriptors(self, *a, **k):
        return self.extract_descriptors(self.data, self.search_range, *a, **k)


class FilmSimulationPatcher:
    """Inject or modify film simulation matrix coefficients."""

    def __init__(self, data: BytesLike = b""):
        self.data = bytearray(_as_bytes(data))

    # internal helpers
    def _find_token_offset(self, token: str) -> int:
        needle = token.encode("ascii")
        pos = bytes(self.data).find(needle)
        if pos == -1:
            raise ValueError(f"Token not found: {token}")
        return pos

    def _matrix_offset(self, token: str, matrix_offset_delta: int = 0) -> int:
        off = self._find_token_offset(token)
        mo = FilmSimulationExtractor._matrix_offset_after(bytes(self.data), off, token)
        return mo + matrix_offset_delta

    def set_matrix(self, token: str, matrix: Sequence, dtype: str = "i",
                   matrix_offset_delta: int = 0) -> "FilmSimulationPatcher":
        if len(matrix) != MATRIX_LEN:
            raise ValueError(f"matrix must have {MATRIX_LEN} coefficients")
        mo = self._matrix_offset(token, matrix_offset_delta)
        if dtype.startswith("f"):
            fmt = "<" + "f" * MATRIX_LEN
            payload = struct.pack(fmt, *[float(x) for x in matrix])
        else:
            fmt = "<" + "i" * MATRIX_LEN
            payload = struct.pack(fmt, *[int(x) for x in matrix])
        if mo + len(payload) > len(self.data):
            self.data.extend(b"\x00" * (mo + len(payload) - len(self.data)))
        self.data[mo:mo + len(payload)] = payload
        return self

    # aliases
    patch_matrix = set_matrix
    replace_matrix = set_matrix
    update_matrix = set_matrix
    inject_matrix = set_matrix
    set_coefficients = set_matrix

    def swap_matrices(self, a: str, b: str, matrix_offset_delta: int = 0) -> "FilmSimulationPatcher":
        descs = FilmSimulationExtractor.extract_descriptors(None, bytes(self.data), (0, len(self.data)))
        ma = None
        mb = None
        for d in descs:
            if d["token"] == a:
                ma = d.get("matrix")
                oa = d["matrix_offset"]
            if d["token"] == b:
                mb = d.get("matrix")
                ob = d["matrix_offset"]
        if ma is None or mb is None:
            raise ValueError("matrix not found for swap")
        self.data[oa:oa + MATRIX_LEN * 4] = struct.pack("<" + "i" * MATRIX_LEN, *mb)
        self.data[ob:ob + MATRIX_LEN * 4] = struct.pack("<" + "i" * MATRIX_LEN, *ma)
        return self

    swap = swap_matrices
    swap_simulations = swap_matrices

    def generate(self) -> bytes:
        return bytes(self.data)

    generate_patch = generate
    build = generate
    apply = generate
    to_bytes = generate
    patched_data = generate
    get_patched_data = generate
    get_data = generate

    def inject_lut(self, token: str, lut: Sequence, offset: Optional[int] = None,
                   dtype: str = "i") -> "FilmSimulationPatcher":
        if offset is None:
            offset = self._matrix_offset(token) + MATRIX_LEN * 4
        if dtype.startswith("f"):
            payload = struct.pack("<" + "f" * len(lut), *[float(x) for x in lut])
        else:
            payload = struct.pack("<" + "i" * len(lut), *[int(x) for x in lut])
        if offset + len(payload) > len(self.data):
            self.data.extend(b"\x00" * (offset + len(payload) - len(self.data)))
        self.data[offset:offset + len(payload)] = payload
        return self


# Backwards-compat alias for registry-style usage
FilmSimulationRegistry = None
try:
    from core.structures.film_simulation import FilmSimulationRegistry as _FSR
    FilmSimulationRegistry = _FSR
except Exception:
    pass
