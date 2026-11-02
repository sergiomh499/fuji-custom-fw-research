"""Pure-Python JPEG/TIFF EXIF Fuji MakerNote recipe reader and writer.

Failure mitigation:
- Volatile / PTP RAM recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
- Firmware repacking / patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from core.recipe import Recipe as _BaseRecipe

BytesLike = Union[bytes, bytearray, memoryview]

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 8: 2, 9: 4, 10: 8, 12: 8}


def _as_bytes(data):
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    return bytes(data)


@dataclass(init=False, eq=True)
class Recipe(_BaseRecipe):
    grain_effect: int = 0
    color_chrome_effect: int = 0
    color_chrome_fx_blue: int = 0
    clarity: int = 0

    _ALIASES = {
        "grain": "grain_effect",
        "grain_strength": "grain_effect",
        "color_chrome": "color_chrome_effect",
        "chrome": "color_chrome_effect",
        "color_chrome_blue": "color_chrome_fx_blue",
        "chrome_blue": "color_chrome_fx_blue",
        "white_balance": "wb_mode",
    }

    def __init__(self, *args, **kwargs):
        base_fields = list(_BaseRecipe.__dataclass_fields__.keys())
        new_order = ["grain_effect", "color_chrome_effect", "color_chrome_fx_blue", "clarity"]
        # alias resolution
        for k in list(kwargs):
            if k in self._ALIASES:
                kwargs[self._ALIASES[k]] = kwargs.pop(k)
        # white balance fine tune tuple
        if "white_balance_fine_tune" in kwargs:
            r, b = kwargs.pop("white_balance_fine_tune")
            kwargs["wb_shift_r"] = r
            kwargs["wb_shift_b"] = b
        base_kw = {}
        new_kw = {}
        for k, v in list(kwargs.items()):
            if k in base_fields:
                base_kw[k] = kwargs.pop(k)
            elif k in new_order:
                new_kw[k] = kwargs.pop(k)
        # positional
        for idx, val in enumerate(args):
            if idx < len(base_fields):
                base_kw[base_fields[idx]] = val
            else:
                new_kw[new_order[idx - len(base_fields)]] = val
        super().__init__(**base_kw)
        for k in new_order:
            setattr(self, k, int(new_kw.get(k, getattr(self, k, 0))))
        # validation
        for attr in ("grain_effect", "color_chrome_effect", "color_chrome_fx_blue"):
            v = getattr(self, attr)
            if v not in (0, 1, 2):
                raise ValueError(f"{attr} must be 0/1/2, got {v}")
        if not (-5 <= self.clarity <= 5):
            raise ValueError(f"clarity out of range: {self.clarity}")

    @property
    def grain(self):
        return self.grain_effect

    @grain.setter
    def grain(self, v):
        self.grain_effect = int(v)

    @property
    def color_chrome(self):
        return self.color_chrome_effect

    @color_chrome.setter
    def color_chrome(self, v):
        self.color_chrome_effect = int(v)

    @property
    def color_chrome_blue(self):
        return self.color_chrome_fx_blue

    @color_chrome_blue.setter
    def color_chrome_blue(self, v):
        self.color_chrome_fx_blue = int(v)

    @property
    def tone(self):
        return (self.highlight, self.shadow)

    @tone.setter
    def tone(self, v):
        self.highlight, self.shadow = v


# ---------- TIFF helpers ----------

def _endian_prefix(data):
    if data[:2] == b"II":
        return "<"
    if data[:2] == b"MM":
        return ">"
    return None


def _read_ifd(buf, endian, offset):
    if offset + 2 > len(buf):
        return {}, 0
    count = struct.unpack(endian + "H", buf[offset:offset + 2])[0]
    entries = {}
    pos = offset + 2
    for _ in range(count):
        if pos + 12 > len(buf):
            break
        tag, typ, cnt, val = struct.unpack(endian + "HHII", buf[pos:pos + 12])
        entries[tag] = (typ, cnt, val)
        pos += 12
    next_off = 0
    if pos + 4 <= len(buf):
        next_off = struct.unpack(endian + "I", buf[pos:pos + 4])[0]
    return entries, next_off


def _read_values(buf, endian, typ, count, val):
    size = TYPE_SIZE.get(typ, 1)
    total = size * count
    if total <= 4:
        raw = struct.pack(endian + "I", val)[:total]
    else:
        if val + total > len(buf):
            return None
        raw = buf[val:val + total]
    if typ == 2:  # ASCII
        try:
            s = raw.split(b"\x00")[0].decode("ascii", "replace")
        except Exception:
            s = ""
        return s
    if typ in (5, 10):  # RATIONAL/SRATIONAL
        out = []
        for i in range(count):
            a, b = struct.unpack(endian + ("II" if typ == 5 else "ii"), raw[i * 8:(i + 1) * 8])
            out.append((a, b))
        return out
    fmt = {1: "B", 3: "H", 4: "I", 7: "B", 8: "h", 9: "i", 12: "d"}.get(typ, "B")
    try:
        return list(struct.unpack(endian + fmt * count, raw))
    except struct.error:
        return None


def _encode_values(typ, vals, endian):
    size = TYPE_SIZE.get(typ, 1)
    if typ == 2:
        if isinstance(vals, str):
            s = vals
        elif isinstance(vals, (list, tuple)) and vals and isinstance(vals[0], str):
            s = vals[0]
        else:
            s = str(vals)
        return (s + "\x00").encode("ascii", "replace")
    if isinstance(vals, (bytes, bytearray, memoryview)):
        return bytes(vals)
    if isinstance(vals, int):
        vals = [vals]
    if typ == 7:
        if isinstance(vals, (list, tuple)) and vals and isinstance(vals[0], int):
            return bytes(vals)
        return bytes(vals)
    fmt = {1: "B", 3: "H", 4: "I", 8: "h", 9: "i", 12: "d"}.get(typ, "B")
    return struct.pack(endian + fmt * len(vals), *vals)


def _encode_ifd(entries, endian, ifd_pos):
    # entries: list of (tag, typ, vals)
    n = len(entries)
    ifd_size = 2 + n * 12 + 4
    raws = [_encode_values(typ, vals, endian) for (_, typ, vals) in entries]
    value_fields = [0] * n
    data_blob = bytearray()
    for i, (tag, typ, vals) in enumerate(entries):
        total = len(raws[i])
        if total <= 4:
            inline = raws[i].ljust(4, b"\x00")
            value_fields[i] = struct.unpack(endian + "I", inline[:4])[0]
        else:
            off = ifd_pos + ifd_size + len(data_blob)
            value_fields[i] = off
            data_blob += raws[i]
    out = bytearray()
    out += struct.pack(endian + "H", n)
    for i, (tag, typ, vals) in enumerate(entries):
        if typ == 2:
            count = len(raws[i])
        elif typ == 7:
            count = len(raws[i])
        else:
            count = len(raws[i]) // TYPE_SIZE.get(typ, 1)
        out += struct.pack(endian + "HHII", tag, typ, count, value_fields[i])
    out += struct.pack(endian + "I", 0)
    out += data_blob
    return bytes(out)


def _find_tiff_bytes(data):
    data = _as_bytes(data)
    if data[:2] in (b"II", b"MM"):
        return data
    # JPEG
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            while i < len(data) and data[i] == 0xFF:
                i += 1
            if i >= len(data):
                break
            marker = data[i]
            i += 1
            if marker == 0xDA:
                break
            if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD9):
                continue
            if i + 2 > len(data):
                break
            length = struct.unpack(">H", data[i:i + 2])[0]
            payload = data[i + 2:i + length]
            if marker == 0xE1 and payload.startswith(b"Exif\x00\x00"):
                return payload[6:]
            i += length
    # search Exif header
    idx = data.find(b"Exif\x00\x00")
    if idx != -1:
        # tiff starts after; find II/MM
        for sig in (b"II*\x00", b"MM\x00*"):
            p = data.find(sig, idx)
            if p != -1:
                return data[p:]
    # search TIFF signature
    for sig in (b"II*\x00", b"MM\x00*"):
        p = data.find(sig)
        if p != -1:
            return data[p:]
    return data


def _parse_tiff(tiff_bytes, recipe=None):
    if recipe is None:
        recipe = Recipe()
    tiff = _as_bytes(tiff_bytes)
    endian = _endian_prefix(tiff)
    if endian is None:
        return recipe
    if len(tiff) < 8:
        return recipe
    magic = struct.unpack(endian + "H", tiff[2:4])[0]
    if magic != 0x002A and magic != 42:
        # maybe big-endian magic check
        pass
    ifd0_offset = struct.unpack(endian + "I", tiff[4:8])[0]
    ifd0, _ = _read_ifd(tiff, endian, ifd0_offset)
    exif_offset = None
    if 0x8769 in ifd0:
        _typ, _cnt, val = ifd0[0x8769]
        vals = _read_values(tiff, endian, _typ, _cnt, val)
        if vals:
            exif_offset = vals[0] if isinstance(vals, list) else vals
    exif_ifd = {}
    if exif_offset:
        exif_ifd, _ = _read_ifd(tiff, endian, exif_offset)
    # MakerNote
    mn_bytes = None
    if 0x927C in exif_ifd:
        _typ, cnt, val = exif_ifd[0x927C]
        if cnt * TYPE_SIZE.get(_typ, 1) <= 4:
            mn_bytes = _as_bytes(struct.pack(endian + "I", val)[:cnt])
        else:
            mn_bytes = tiff[val:val + cnt]
    if not mn_bytes:
        return recipe
    # parse makernote
    if mn_bytes[:8] == b"FUJIFILM":
        try:
            mn_ifd_offset = struct.unpack("<I", mn_bytes[8:12])[0]
        except Exception:
            mn_ifd_offset = 12
        mn_endian = "<"
        mn_ifd, _ = _read_ifd(mn_bytes, mn_endian, mn_ifd_offset)
    else:
        mn_endian = endian
        mn_ifd, _ = _read_ifd(mn_bytes, mn_endian, 0)
    buf = mn_bytes

    def gv(tag):
        if tag not in mn_ifd:
            return None
        typ, cnt, val = mn_ifd[tag]
        return _read_values(buf, mn_endian, typ, cnt, val)

    fs = gv(0x1001)
    if fs is not None:
        if isinstance(fs, str):
            key = fs.strip().lower()
            try:
                from core.recipe import FILM_SIMULATIONS
                if key in FILM_SIMULATIONS:
                    recipe.film_simulation = FILM_SIMULATIONS[key]
                else:
                    recipe.film_simulation = int(fs)
            except Exception:
                try:
                    recipe.film_simulation = int(fs)
                except Exception:
                    pass
        else:
            try:
                recipe.film_simulation = int(fs if not isinstance(fs, list) else fs[0])
            except Exception:
                pass
    dr = gv(0x1002)
    if dr is not None:
        v = dr[0] if isinstance(dr, list) else dr
        recipe.dynamic_range = int(v)
    wb = gv(0x1003)
    if wb is not None:
        v = wb if not isinstance(wb, list) else (wb[0] if wb else wb)
        if isinstance(v, str):
            key = v.strip().lower().replace(" ", "")
            from core.recipe import WB_MODES
            if key in WB_MODES:
                recipe.wb_mode = WB_MODES[key]
            else:
                try:
                    recipe.wb_mode = int(v)
                except Exception:
                    pass
        else:
            try:
                recipe.wb_mode = int(v)
            except Exception:
                pass
    color = gv(0x1004)
    if color is not None:
        v = color[0] if isinstance(color, list) else color
        recipe.color = int(v)
    tone = gv(0x1005)
    if tone is not None:
        if isinstance(tone, list):
            if len(tone) > 0:
                recipe.highlight = int(tone[0])
            if len(tone) > 1:
                recipe.shadow = int(tone[1])
        else:
            recipe.highlight = int(tone)
    sharp = gv(0x1006)
    if sharp is not None:
        v = sharp[0] if isinstance(sharp, list) else sharp
        recipe.sharpness = int(v)
    nr = gv(0x100B)
    if nr is not None:
        v = nr[0] if isinstance(nr, list) else nr
        recipe.noise_reduction = int(v)
    wbft = gv(0x1040)
    if wbft is not None:
        if isinstance(wbft, list):
            if len(wbft) > 0:
                recipe.wb_shift_r = int(wbft[0])
            if len(wbft) > 1:
                recipe.wb_shift_b = int(wbft[1])
        else:
            recipe.wb_shift_r = int(wbft)
    grain = gv(0x1047)
    if grain is not None:
        v = grain[0] if isinstance(grain, list) else grain
        recipe.grain_effect = int(v)
    chrome = gv(0x1048)
    if chrome is not None:
        v = chrome[0] if isinstance(chrome, list) else chrome
        recipe.color_chrome_effect = int(v)
    chrome_blue = gv(0x1049)
    if chrome_blue is not None:
        v = chrome_blue[0] if isinstance(chrome_blue, list) else chrome_blue
        recipe.color_chrome_fx_blue = int(v)
    clarity = gv(0x104A)
    if clarity is not None:
        v = clarity[0] if isinstance(clarity, list) else clarity
        recipe.clarity = int(v)
    return recipe


def _build_tiff(recipe):
    r = recipe
    mn_entries = [
        (0x1001, 3, [int(r.film_simulation)]),
        (0x1002, 3, [int(r.dynamic_range)]),
        (0x1003, 3, [int(r.wb_mode)]),
        (0x1004, 8, [int(r.color)]),
        (0x1005, 8, [int(r.highlight), int(r.shadow)]),
        (0x1006, 8, [int(r.sharpness)]),
        (0x100B, 8, [int(r.noise_reduction)]),
        (0x1040, 8, [int(r.wb_shift_r), int(r.wb_shift_b)]),
        (0x1047, 3, [int(r.grain_effect)]),
        (0x1048, 3, [int(r.color_chrome_effect)]),
        (0x1049, 3, [int(r.color_chrome_fx_blue)]),
        (0x104A, 8, [int(r.clarity)]),
    ]
    mn_ifd_pos = 12
    mn_ifd_bytes = _encode_ifd(mn_entries, "<", mn_ifd_pos)
    mn_bytes = b"FUJIFILM" + struct.pack("<I", 12) + mn_ifd_bytes

    ifd0_pos = 8
    ifd0_entries = [(0x8769, 4, [26])]
    ifd0_bytes = _encode_ifd(ifd0_entries, "<", ifd0_pos)

    exif_ifd_pos = ifd0_pos + len(ifd0_bytes)
    exif_entries = [(0x927C, 7, mn_bytes)]
    exif_bytes = _encode_ifd(exif_entries, "<", exif_ifd_pos)

    header = b"II*\x00" + struct.pack("<I", ifd0_pos)
    return header + ifd0_bytes + exif_bytes


class FujiMakerNoteReader:
    def __init__(self, data=None):
        self.data = data

    def read(self, data=None):
        if isinstance(self, (bytes, bytearray, memoryview)):
            data = self
            self = None
        d = data if data is not None else (getattr(self, "data", None) if self is not None else None)
        tiff = _find_tiff_bytes(d)
        return _parse_tiff(tiff)

    def extract(self, data=None):
        if isinstance(self, (bytes, bytearray, memoryview)):
            data = self
            self = None
        d = data if data is not None else (getattr(self, "data", None) if self is not None else None)
        tiff = _find_tiff_bytes(d)
        return _parse_tiff(tiff)

    parse = extract
    from_bytes = staticmethod(lambda data: FujiMakerNoteReader(data).extract())
    read_recipe = read

    @classmethod
    def extract_recipe(cls, data):
        return cls(data).read()

    @classmethod
    def extract_recipe_from_bytes(cls, data):
        return cls(data).read()


class FujiMakerNoteWriter:
    def __init__(self, recipe=None, data=None):
        self.recipe = recipe
        self.data = data

    @staticmethod
    def write(data, recipe):
        data = _as_bytes(data)
        recipe = recipe
        tiff = _build_tiff(recipe)
        app1_payload = b"Exif\x00\x00" + tiff
        app1_segment = b"\xff\xe1" + struct.pack(">H", len(app1_payload) + 2) + app1_payload

        if data[:2] != b"\xff\xd8":
            # wrap raw data as JPEG? assume provided is JPEG; if not, prepend SOI
            data = b"\xff\xd8" + data
        out = bytearray(data[:2])
        i = 2
        written = False
        sos_pos = None
        while i < len(data):
            if data[i] != 0xFF:
                break
            while i < len(data) and data[i] == 0xFF:
                i += 1
            if i >= len(data):
                break
            marker = data[i]
            i += 1
            if marker == 0xDA:
                sos_pos = i - 2
                break
            if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD9):
                out += bytes([0xFF, marker])
                continue
            if i + 2 > len(data):
                break
            length = struct.unpack(">H", data[i:i + 2])[0]
            payload = data[i + 2:i + length]
            if marker == 0xE1 and payload.startswith(b"Exif\x00\x00"):
                if not written:
                    out += app1_segment
                    written = True
                # skip old
            else:
                out += bytes([0xFF, marker]) + data[i:i + length]
            i += length
        if not written:
            out += app1_segment
            written = True
        if sos_pos is not None:
            out += data[sos_pos:]
        else:
            # no SOS found; append rest
            out += data[i:]
        return bytes(out)

    patch = write
    inject = write
    apply = write

    def write_jpeg(self, data=None, recipe=None):
        d = data if data is not None else self.data
        r = recipe if recipe is not None else self.recipe
        return self.write(d, r)


def read_recipe(data):
    return FujiMakerNoteReader(data).read()


def write_recipe(data, recipe):
    return FujiMakerNoteWriter.write(data, recipe)


# aliases
FujiMakerNoteReader.extract_recipe = FujiMakerNoteReader.read
FujiMakerNoteReader.parse_recipe = FujiMakerNoteReader.read


# Extra static convenience wrappers
_original_write = FujiMakerNoteWriter.write
@staticmethod
def _write_jpeg_static(data, recipe=None):
    return FujiMakerNoteWriter.write(data, recipe)
FujiMakerNoteWriter.write_jpeg = _write_jpeg_static
