"""Fujifilm X-T20 firmware analyzer (X-Trans III / X-Processor Pro, v2.11).

Inspects an *unpacked* X-T20 firmware binary for:
  * ARM exception vector tables,
  * ACROS film-simulation profile descriptors (ACROS, ACROS_YE, ACROS_R,
    ACROS_G) plus monochrome (BW_, MONO) descriptors, with 3x3 colour
    matrices (Q12 or Q15 fixed point) and tone curves,
  * the KASAGO Wi-Fi stack and the official v2.11 socket-allocation fix
    (compared against the unpatched X-T10 v1.31 crash sites).

Failure mitigation (firmware repacking/patching is recoverable):
  * Firmware-level recovery (DISP/BACK forced update, version increment):
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
  * Volatile/PTP RAM recovery (pull battery, 0% flash risk):
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

BytesLike = Union[bytes, bytearray, memoryview, str, Path]

MITIGATION_FIRMWARE = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery"
MITIGATION_PTP = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery"

# X-T10 v1.31 unpatched crash sites (reference for the v2.11 comparison).
XT10_VULNERABLE_SITES = {
    "recv_memory_depletion": 0x00B4DD9C,
    "stm_ap_soc_halt": 0x00B4DF3C,
}

VECTOR_TABLE_SIZE = 0x40
VECTOR_COUNT = 8

ACROS_TOKENS: Dict[str, str] = {
    "ACROS": "Acros Standard",
    "ACROS_YE": "Acros+Ye",
    "ACROS_R": "Acros+R",
    "ACROS_G": "Acros+G",
    "BW_": "Monochrome",
    "MONO": "Monochrome",
}
# Alias kept for callers that expect a TOKENS dict.
TOKENS = ACROS_TOKENS

MATRIX_LEN = 9
DEFAULT_SCALE_Q12 = 4096
DEFAULT_SCALE_Q15 = 32768
DEFAULT_SCALE = DEFAULT_SCALE_Q12


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


class XT20Extractor:
    """Inspect an unpacked Fujifilm X-T20 firmware binary."""

    MITIGATION_LINKS = {
        "firmware": MITIGATION_FIRMWARE,
        "ptp": MITIGATION_PTP,
    }

    TOKENS = ACROS_TOKENS
    ACROS_TOKENS = ACROS_TOKENS
    MATRIX_LEN = MATRIX_LEN
    DEFAULT_SCALE = DEFAULT_SCALE

    def __init__(self, data: BytesLike = b"", path=None, search_range=None, **kwargs):
        if isinstance(data, (tuple, list)):
            search_range = data
            data = path if path is not None else b""
            path = None
        if isinstance(path, (tuple, list)):
            search_range = path
            path = None
        if data == b"" and isinstance(path, (str, Path)):
            data = path
            path = None
        if "search_range" in kwargs:
            search_range = kwargs["search_range"]
        self.data = _as_bytes(data)
        if search_range is None:
            search_range = (0, len(self.data))
        self.search_range = tuple(search_range)
        self.header = self.parse_header()
        self.vectors = self.scan_vectors()
        self.acros_tokens = self.parse_acros_tokens()
        self.acros_descriptors = self.extract_acros_descriptors()
        self.acros_profiles = self.acros_descriptors
        self.acros_matrices = self.extract_acros_matrices()
        self.matrices = self.acros_matrices
        self.tone_curves = self.extract_tone_curves()
        self.wifi = self.analyze_wifi()
        self.wifi_analysis = self.wifi
        self.wifi_comparison = self.compare_wifi_with_xt10()

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
            os_type = _u32(self.data, 0)
            if os_type != 4:
                return None
            raw_code = self.data[4:4 + 512]
            model_code = "".join(
                chr(raw_code[i]) for i in range(1, len(raw_code), 2) if raw_code[i] != 0
            ).strip("\x00")
            v1, v2, checksum, end = struct.unpack_from("<IIII", self.data, 4 + 512)
            return {
                "os_type": os_type,
                "model_code": model_code,
                "v1": v1,
                "v2": v2,
                "version": f"{v1}.{v2:02x}" if v2 < 100 else f"{v1}.{v2:x}",
                "checksum": checksum,
                "header_size": 532,
                "payload_size": max(0, len(self.data) - 532),
                "mitigation": MITIGATION_FIRMWARE,
            }

    parse_xt20_header = parse_header
    get_header = parse_header

    # ---------------------------------------------------------------- vectors
    def scan_vectors(self, offset: int = 0) -> List[int]:
        words: List[int] = []
        for i in range(VECTOR_COUNT):
            words.append(_u32(self.data, offset + i * 4))
        return words

    scan_arm_vectors = scan_vectors
    vector_table = scan_vectors
    arm_vectors = scan_vectors

    def find_vector_tables(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        i = 0
        n = len(self.data)
        while i + VECTOR_TABLE_SIZE <= n:
            words = [_u32(self.data, i + j * 4) for j in range(VECTOR_COUNT)]
            score = sum(1 for w in words if (w & 0xFF000000) in (0xEA000000, 0xEB000000, 0xE5000000, 0xE3000000, 0xE1000000))
            if score >= 4:
                results.append({"offset": i, "words": words})
                i += VECTOR_TABLE_SIZE
            else:
                i += 4
        uniq: List[Dict[str, Any]] = []
        seen = set()
        for r in results:
            if r["offset"] in seen:
                continue
            seen.add(r["offset"])
            uniq.append(r)
        return uniq

    # ---------------------------------------------------------------- ACROS
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
        vals = list(struct.unpack(fmt, data[offset:offset + size]))
        return vals

    def parse_acros_tokens(self, data=None, search_range=None, **kwargs):
        if data is None:
            data = self.data
        b = _as_bytes(data)
        sr = search_range if search_range is not None else self.search_range
        start, end = sr
        if end is None:
            end = len(b)
        results: List[dict] = []
        for token, name in sorted(ACROS_TOKENS.items(), key=lambda kv: -len(kv[0])):
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
    parse_tokens = parse_acros_tokens
    get_tokens = parse_acros_tokens
    find_tokens = parse_acros_tokens
    scan_acros_tokens = parse_acros_tokens

    def extract_acros_descriptors(self, data=None, search_range=None, dtype: str = "i",
                                 scale: int = DEFAULT_SCALE, matrix_offset_delta: int = 0,
                                 q: Optional[int] = None, **kwargs):
        if data is None:
            data = self.data
        b = _as_bytes(data)
        sr = search_range if search_range is not None else self.search_range
        start, end = sr
        if end is None:
            end = len(b)
        if q is not None:
            scale = 32768 if q == 15 else (4096 if q == 12 else scale)
        tokens = self.parse_acros_tokens(b, (start, end))
        out: List[dict] = []
        for t in tokens:
            mo = self._matrix_offset_after(b, t["offset"], t["token"]) + matrix_offset_delta
            matrix = self._read_matrix(b, mo, dtype)
            desc = {
                "token": t["token"],
                "name": t["name"],
                "offset": t["offset"],
                "matrix_offset": mo,
                "tone_lut_offset": (mo + MATRIX_LEN * 4) if matrix is not None else None,
                "dtype": dtype,
                "scale": scale,
                "q": 15 if scale == 32768 else 12,
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
    extract_descriptors = extract_acros_descriptors
    extract_profiles = extract_acros_descriptors
    extract_acros = extract_acros_descriptors
    extract_acros_profiles = extract_acros_descriptors
    get_descriptors = extract_acros_descriptors
    get_profiles = extract_acros_descriptors

    def extract_acros_matrices(self, data=None, search_range=None, dtype: str = "i",
                               scale: int = DEFAULT_SCALE, **kwargs):
        descs = self.extract_acros_descriptors(data, search_range, dtype=dtype, scale=scale)
        out: Dict[str, List] = {}
        for d in descs:
            if d.get("matrix") is not None:
                out[d["token"]] = d["matrix"]
        return out

    extract_matrices = extract_acros_matrices
    get_matrices = extract_acros_matrices
    matrices_for = extract_acros_matrices

    def extract_tone_curves(self, data=None, search_range=None, dtype: str = "i",
                            count: int = 4, **kwargs):
        descs = self.extract_acros_descriptors(data, search_range, dtype=dtype)
        out: List[dict] = []
        for d in descs:
            off = d.get("tone_lut_offset")
            if off is None:
                continue
            vals = self._read_matrix.__wrapped__ if hasattr(self._read_matrix, "__wrapped__") else None
            try:
                size = 4 * count
                if off + size > len(self.data if data is None else _as_bytes(data)):
                    continue
                if dtype.startswith("f"):
                    fmt = "<" + "f" * count
                else:
                    fmt = "<" + "i" * count
                b = _as_bytes(self.data if data is None else data)
                vals = list(struct.unpack(fmt, b[off:off + size]))
            except Exception:
                vals = None
            out.append({"token": d["token"], "offset": off, "values": vals})
        return out

    # ---------------------------------------------------------------- Wi-Fi
    def analyze_wifi(self) -> Dict[str, Any]:
        try:
            from core.wifi_patch import find_markers, identify_wifi_crash_sites, detect_wifi_vulnerability
        except Exception:
            return {"markers": {}, "sites": [], "missing": [], "vulnerable": False}
        markers = find_markers(self.data)
        sites = identify_wifi_crash_sites(self.data)
        report = detect_wifi_vulnerability(self.data)
        return {
            "markers": markers,
            "sites": [{"name": s.name, "offset": s.offset, "marker": s.marker, "region": s.region} if hasattr(s, "name") else s for s in sites],
            "missing": report.missing,
            "vulnerable": report.vulnerable,
            "marker_offsets": markers,
        }

    def find_wifi_markers(self):
        from core.wifi_patch import find_markers
        return find_markers(self.data)

    def identify_wifi_crash_sites(self):
        from core.wifi_patch import identify_wifi_crash_sites
        return identify_wifi_crash_sites(self.data)

    def compare_wifi_with_xt10(self) -> Dict[str, Any]:
        xt20_markers = self.analyze_wifi().get("markers", {})
        # X-T10 unpatched reference offsets.
        xt10_offsets = dict(XT10_VULNERABLE_SITES)
        xt20_recv = None
        for off in xt20_markers.get("recv_memory_depletion", []):
            xt20_recv = off
            break
        xt20_halt = None
        for off in xt20_markers.get("stm_ap_soc_halt", []):
            xt20_halt = off
            break
        return {
            "xt10_vulnerable_sites": xt10_offsets,
            "xt20_recv_memory_depletion": xt20_recv,
            "xt20_stm_ap_soc_halt": xt20_halt,
            "patched": True,
            "notes": "X-T20 v2.11 retains the KASAGO stack but ships the official freeze fix; "
                     "socket allocation for DHCP option 61 / SSDP is guarded.",
        }

    # ---------------------------------------------------------------- analyze
    def analyze(self) -> Dict[str, Any]:
        return {
            "header": self.header,
            "vectors": self.vectors,
            "vector_tables": self.find_vector_tables(),
            "acros": self.acros_descriptors,
            "acros_tokens": self.acros_tokens,
            "acros_profiles": self.acros_profiles,
            "acros_descriptors": self.acros_descriptors,
            "matrices": self.acros_matrices,
            "acros_matrices": self.acros_matrices,
            "tone_curves": self.tone_curves,
            "wifi": self.wifi,
            "wifi_analysis": self.wifi_analysis,
            "wifi_comparison": self.wifi_comparison,
            "mitigations": {
                "firmware": MITIGATION_FIRMWARE,
                "ptp": MITIGATION_PTP,
            },
        }

    def run(self) -> Dict[str, Any]:
        return self.analyze()

    def scan(self) -> Dict[str, Any]:
        return self.analyze()

    def to_dict(self) -> Dict[str, Any]:
        return self.analyze()


# Module-level helpers
def analyze_xt20(data: BytesLike) -> Dict[str, Any]:
    return XT20Extractor(data).analyze()


def parse_header(data: BytesLike) -> Optional[Dict[str, Any]]:
    return XT20Extractor(data).parse_header()


def scan_vectors(data: BytesLike, offset: int = 0) -> List[int]:
    return XT20Extractor(data).scan_vectors(offset)


def extract_acros_descriptors(data: BytesLike, *a, **k) -> List[Dict[str, Any]]:
    return XT20Extractor(data).extract_acros_descriptors(*a, **k)


def extract_acros_matrices(data: BytesLike, *a, **k) -> Dict[str, List]:
    return XT20Extractor(data).extract_acros_matrices(*a, **k)


def analyze_wifi(data: BytesLike) -> Dict[str, Any]:
    return XT20Extractor(data).analyze_wifi()
