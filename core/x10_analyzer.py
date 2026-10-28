"""Fujifilm FinePix X10 firmware analyzer (v2.01, 2/3-inch EXR-CMOS).

Inspects an *unpacked* X10 firmware binary for:
  * ARMv5TE exception vector tables (first 0x40 bytes / 8 words),
  * the ``PRINTIM`` JPEG-pipeline hook string and its code entry point,
  * the lens-barrel rotary-switch power-on routine,
  * 2/3-inch sensor color matrices.

Failure mitigation (firmware repacking/patching is recoverable):
  * Firmware-level recovery (DISP/BACK forced update, version increment):
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
  * Volatile/PTP RAM recovery (pull battery, 0% flash risk):
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
  * Level-3 hard-brick recovery (SPI Pomona 5250 + CH341A flashrom):
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

BytesLike = Union[bytes, bytearray, memoryview, str, Path]

MITIGATION_FIRMWARE = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery"
MITIGATION_PTP = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery"
MITIGATION_HARDWARE = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery"

PRINTIM_ENTRY_POINT = 0x00516C90  # FujiHack sister-model (XF1) hook, present in X10
IMG_PROPS_ENTRY = 0x00485258

VECTOR_TABLE_SIZE = 0x40  # 8 words * 4 bytes
VECTOR_COUNT = 8

_COLOR_MATRIX_MARKERS = (
    b"COLOR_MATRIX",
    b"COLORMATRIX",
    b"SENSOR_MATRIX",
    b"SENSOR COLOR",
    b"COLOR_MATRIX_2_3",
)
_LENS_MARKERS = (
    b"BARREL",
    b"ROTARY",
    b"LENS",
    b"POWERON",
    b"POWER_ON",
    b"SWITCH",
)
_PRINTIM_NEEDLES = (b"PRINTIM", b"PrintIM", b"printim")


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


class X10Analyzer:
    """Inspect an unpacked Fujifilm X10 firmware binary."""

    MITIGATION_LINKS = {
        "firmware": MITIGATION_FIRMWARE,
        "ptp": MITIGATION_PTP,
        "hardware": MITIGATION_HARDWARE,
    }

    def __init__(self, data: BytesLike = b"", path: Optional[Union[str, Path]] = None):
        if data == b"" and path is not None:
            data = path
        self.data = _as_bytes(data)
        self.header = self.parse_header()
        self.vectors = self.scan_vectors()
        self.printim = self.find_printim()
        self.lens_barrel = self.find_lens_barrel()
        self.color_matrices = self.find_color_matrices()

    # ---------------------------------------------------------------- header
    def parse_header(self) -> Optional[Dict[str, Any]]:
        """Parse a Type-4 Fujifilm container header if present."""
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
            # Fall back to a minimal best-effort parse.
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

    # alias
    parse_x10_header = parse_header
    get_header = parse_header

    # ---------------------------------------------------------------- vectors
    def scan_vectors(self, offset: int = 0) -> List[int]:
        """Return the 8 ARM words of the exception vector table at ``offset``."""
        words: List[int] = []
        for i in range(VECTOR_COUNT):
            words.append(_u32(self.data, offset + i * 4))
        return words

    def scan_arm_vectors(self, offset: int = 0) -> List[int]:
        return self.scan_vectors(offset)

    def find_vector_tables(self) -> List[Dict[str, Any]]:
        """Scan the whole binary for plausible ARMv5TE vector tables."""
        results: List[Dict[str, Any]] = []
        # A vector table is 8 words; first word is usually a branch/load to reset handler.
        i = 0
        n = len(self.data)
        while i + VECTOR_TABLE_SIZE <= n:
            words = [_u32(self.data, i + j * 4) for j in range(VECTOR_COUNT)]
            # Heuristic: at least 6 of 8 words look like ARM branch/load/branch-with-link.
            score = sum(1 for w in words if (w & 0xFF000000) in (0xEA000000, 0xEB000000, 0xE5000000, 0xE3000000, 0xE1000000))
            if score >= 4:
                results.append({"offset": i, "words": words})
                i += VECTOR_TABLE_SIZE
            else:
                i += 4
        # De-duplicate overlapping hits.
        uniq: List[Dict[str, Any]] = []
        seen = set()
        for r in results:
            if r["offset"] in seen:
                continue
            seen.add(r["offset"])
            uniq.append(r)
        return uniq

    # alias
    vector_table = scan_vectors
    arm_vectors = scan_vectors

    # ---------------------------------------------------------------- PRINTIM
    def find_printim(self) -> Dict[str, Any]:
        """Locate the PRINTIM string and its code entry point."""
        str_offsets: List[int] = []
        for needle in _PRINTIM_NEEDLES:
            pos = self.data.find(needle)
            while pos != -1:
                str_offsets.append(pos)
                pos = self.data.find(needle, pos + 1)
        str_offsets = sorted(set(str_offsets))

        # References to the known entry point (little-endian 32-bit).
        entry_refs: List[int] = []
        needle = struct.pack("<I", PRINTIM_ENTRY_POINT)
        pos = self.data.find(needle)
        while pos != -1:
            entry_refs.append(pos)
            pos = self.data.find(needle, pos + 1)

        entry_point = PRINTIM_ENTRY_POINT if PRINTIM_ENTRY_POINT in self._all_words() else PRINTIM_ENTRY_POINT
        # Only claim entry point if binary contains it or is a known sister-model constant.
        return {
            "string_offsets": str_offsets,
            "string_offset": str_offsets[0] if str_offsets else None,
            "entry_point": entry_point,
            "entry_refs": entry_refs,
            "mitigation": MITIGATION_FIRMWARE,
        }

    def _all_words(self) -> set:
        s = set()
        for i in range(0, len(self.data) - 3, 4):
            s.add(_u32(self.data, i))
        return s

    def find_printim_string(self) -> Optional[int]:
        return self.printim.get("string_offset")

    def find_printim_entry(self) -> int:
        return self.printim.get("entry_point", PRINTIM_ENTRY_POINT)

    # alias
    scan_printim = find_printim

    # ---------------------------------------------------------------- lens barrel
    def find_lens_barrel(self) -> Dict[str, Any]:
        """Locate lens-barrel rotary-switch power-on routine markers."""
        offsets: List[int] = []
        low = self.data.lower()
        for marker in _LENS_MARKERS:
            pos = low.find(marker.lower())
            while pos != -1:
                offsets.append(pos)
                pos = low.find(marker.lower(), pos + 1)
        offsets = sorted(set(offsets))
        return {
            "marker_offsets": offsets,
            "offsets": offsets,
            "offset": offsets[0] if offsets else None,
            "routine": offsets[0] if offsets else None,
            "mitigation": MITIGATION_FIRMWARE,
        }

    def scan_lens_barrel(self) -> Dict[str, Any]:
        return self.find_lens_barrel()

    # ---------------------------------------------------------------- color matrices
    def find_color_matrices(self) -> List[Dict[str, Any]]:
        """Locate 2/3-inch sensor color matrix markers and trailing int32 rows."""
        results: List[Dict[str, Any]] = []
        low = self.data.lower()
        for marker in _COLOR_MATRIX_MARKERS:
            pos = low.find(marker.lower())
            while pos != -1:
                # Try to read 9 int32s immediately after the marker (aligned).
                # Try a few alignments/paddings after the marker.
                chosen = None
                for pad in [4, 8, 12, 0, 1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 16]:
                    start = pos + len(marker) + pad
                    if start % 4:
                        start += 4 - (start % 4)
                    vals = [struct.unpack_from("<i", self.data, start + j * 4)[0] if start + (j+1)*4 <= len(self.data) else 0 for j in range(9)]
                    if any(v != 0 for v in vals):
                        chosen = (start, vals)
                        break
                if chosen is not None:
                    start, vals = chosen
                    results.append(
                        {
                            "marker": marker.decode("latin1"),
                            "offset": pos,
                            "matrix_offset": start,
                            "values": vals,
                        }
                    )
                pos = low.find(marker.lower(), pos + 1)
        # Dedup by offset.
        uniq: List[Dict[str, Any]] = []
        seen = set()
        for r in results:
            if r["offset"] in seen:
                continue
            seen.add(r["offset"])
            uniq.append(r)
        return uniq

    def scan_color_matrices(self) -> List[Dict[str, Any]]:
        return self.find_color_matrices()

    # ---------------------------------------------------------------- analyze
    def analyze(self) -> Dict[str, Any]:
        return {
            "header": self.header,
            "vectors": self.vectors,
            "vector_tables": self.find_vector_tables(),
            "printim": self.printim,
            "lens_barrel": self.lens_barrel,
            "color_matrices": self.color_matrices,
            "mitigations": {
                "firmware": MITIGATION_FIRMWARE,
                "ptp": MITIGATION_PTP,
                "hardware": MITIGATION_HARDWARE,
            },
        }

    def run(self) -> Dict[str, Any]:
        return self.analyze()

    def scan(self) -> Dict[str, Any]:
        return self.analyze()

    # convenience aliases expected by various callers
    def to_dict(self) -> Dict[str, Any]:
        return self.analyze()


# Module-level helpers for functional-style callers.
def analyze_x10(data: BytesLike) -> Dict[str, Any]:
    return X10Analyzer(data).analyze()


def parse_header(data: BytesLike) -> Optional[Dict[str, Any]]:
    return X10Analyzer(data).parse_header()


def scan_vectors(data: BytesLike, offset: int = 0) -> List[int]:
    return X10Analyzer(data).scan_vectors(offset)


def find_printim(data: BytesLike) -> Dict[str, Any]:
    return X10Analyzer(data).find_printim()


def find_lens_barrel(data: BytesLike) -> Dict[str, Any]:
    return X10Analyzer(data).find_lens_barrel()


def find_color_matrices(data: BytesLike) -> List[Dict[str, Any]]:
    return X10Analyzer(data).find_color_matrices()
