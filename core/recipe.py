"""Recipe persistence & SD file export for Fujifilm custom recipes (C1-C7).

Binary layout (128 bytes, little-endian) documented in docs/RECIPE_STORAGE_SPEC.md.
"""

import configparser
import io
import os
import struct
import zlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

BytesLike = Union[bytes, bytearray, memoryview]

SLOT_NAMES = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]

FILM_SIMULATIONS: Dict[str, int] = {
    "provia": 0,
    "standard": 0,
    "velvia": 1,
    "vivid": 1,
    "astia": 2,
    "soft": 2,
    "classic chrome": 3,
    "classic_chrome": 3,
    "chrome": 3,
    "pro neg. hi": 4,
    "pro_neg_hi": 4,
    "pro neg. std": 5,
    "pro_neg_std": 5,
    "monochrome": 6,
    "bw": 6,
    "sepia": 7,
    "acros": 8,
    "eterna": 9,
}
FILM_SIM_NAMES: Dict[int, str] = {
    0: "Provia", 1: "Velvia", 2: "Astia", 3: "Classic Chrome",
    4: "Pro Neg. Hi", 5: "Pro Neg. Std", 6: "Monochrome",
    7: "Sepia", 8: "Acros", 9: "Eterna",
}

WB_MODES: Dict[str, int] = {
    "auto": 0, "daylight": 1, "shade": 2, "fluorescent1": 3,
    "fluorescent2": 4, "fluorescent3": 5, "incandescent": 6,
    "underwater": 7, "kelvin": 8, "custom": 9,
}
WB_MODE_NAMES: Dict[int, str] = {v: k for k, v in WB_MODES.items()}

DR_CODES = {100: 0, 200: 1, 400: 2}
DR_VALUES = {0: 100, 1: 200, 2: 400}

MAGIC = b"FJRC"
VERSION = 1
RECORD_SIZE = 128


def _as_bytes(data):
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    if hasattr(data, "data"):
        return bytes(data.data)
    return bytes(data)


def _norm_slot(slot):
    if isinstance(slot, int):
        if 1 <= slot <= 7:
            return f"C{slot}"
        raise ValueError(f"invalid slot: {slot}")
    s = str(slot).strip().upper()
    if s in SLOT_NAMES:
        return s
    if s.startswith("C") and s[1:].isdigit():
        n = int(s[1:])
        if 1 <= n <= 7:
            return f"C{n}"
    if s.isdigit():
        n = int(s)
        if 1 <= n <= 7:
            return f"C{n}"
    # "CUSTOM 1" / "CUSTOM1"
    low = s.lower().replace(" ", "")
    if low.startswith("custom") and low[6:].isdigit():
        n = int(low[6:])
        if 1 <= n <= 7:
            return f"C{n}"
    raise ValueError(f"invalid slot: {slot!r}")


def _film_sim_id(value):
    if isinstance(value, bool):
        raise ValueError("film_simulation must be int or str")
    if isinstance(value, int):
        if value not in FILM_SIM_NAMES:
            raise ValueError(f"unknown film simulation id: {value}")
        return value
    if isinstance(value, str):
        key = value.strip().lower()
        if key in FILM_SIMULATIONS:
            return FILM_SIMULATIONS[key]
        # try int
        try:
            n = int(key)
            if n in FILM_SIM_NAMES:
                return n
        except ValueError:
            pass
        raise ValueError(f"unknown film simulation: {value!r}")
    raise ValueError(f"film_simulation must be int or str, got {type(value)}")


def _wb_mode_id(value):
    if isinstance(value, bool):
        raise ValueError("wb_mode must be int or str")
    if isinstance(value, int):
        if value not in WB_MODE_NAMES:
            raise ValueError(f"unknown wb mode id: {value}")
        return value
    if isinstance(value, str):
        key = value.strip().lower().replace(" ", "")
        if key in WB_MODES:
            return WB_MODES[key]
        try:
            n = int(key)
            if n in WB_MODE_NAMES:
                return n
        except ValueError:
            pass
        raise ValueError(f"unknown wb mode: {value!r}")
    raise ValueError(f"wb_mode must be int or str")


@dataclass
class Recipe:
    name: str = "Custom"
    slot: Optional[str] = None
    film_simulation: int = 0
    dynamic_range: int = 100
    wb_mode: Union[int, str] = 0
    wb_kelvin: int = 5500
    wb_shift_r: int = 0
    wb_shift_b: int = 0
    highlight: int = 0
    shadow: int = 0
    color: int = 0
    sharpness: int = 0
    noise_reduction: int = 0

    def __post_init__(self):
        self.name = str(self.name)
        if self.slot is not None:
            self.slot = _norm_slot(self.slot)
        self.film_simulation = _film_sim_id(self.film_simulation)
        if isinstance(self.wb_mode, str):
            self.wb_mode = _wb_mode_id(self.wb_mode)
        else:
            self.wb_mode = _wb_mode_id(self.wb_mode)
        if self.dynamic_range not in (100, 200, 400):
            raise ValueError(f"dynamic_range must be 100/200/400, got {self.dynamic_range}")
        if not (2500 <= self.wb_kelvin <= 10000):
            raise ValueError(f"wb_kelvin out of range: {self.wb_kelvin}")
        for attr in ("wb_shift_r", "wb_shift_b"):
            v = getattr(self, attr)
            if not (-9 <= v <= 9):
                raise ValueError(f"{attr} out of range: {v}")
        for attr in ("highlight", "shadow", "color", "sharpness", "noise_reduction"):
            v = getattr(self, attr)
            if not (-2 <= v <= 2):
                raise ValueError(f"{attr} out of range: {v}")
        if len(self.name.encode("utf-8")) > 32:
            # truncate to fit
            self.name = self.name.encode("utf-8")[:32].decode("utf-8", "ignore")

    @property
    def film_simulation_name(self) -> str:
        return FILM_SIM_NAMES.get(self.film_simulation, "Unknown")

    @property
    def wb_mode_name(self) -> str:
        return WB_MODE_NAMES.get(self.wb_mode, "unknown")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["film_simulation_name"] = self.film_simulation_name
        d["wb_mode_name"] = self.wb_mode_name
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Recipe":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    # convenience aliases
    def to_bytes(self):
        return RecipeSerializer.to_bytes(self)

    @classmethod
    def from_bytes(cls, data):
        return RecipeSerializer.from_bytes(data)

    def to_text(self):
        return RecipeSerializer.to_text(self)

    @classmethod
    def from_text(cls, text):
        return RecipeSerializer.from_text(text)


class RecipeSerializer:
    @staticmethod
    def _validate_recipe(recipe):
        if not isinstance(recipe, Recipe):
            raise TypeError("recipe must be Recipe")

    @staticmethod
    def to_bytes(recipe: Recipe) -> bytes:
        RecipeSerializer._validate_recipe(recipe)
        dr_code = DR_CODES[recipe.dynamic_range]
        name_b = recipe.name.encode("utf-8")[:32]
        name_b = name_b + b"\x00" * (32 - len(name_b))
        buf = bytearray(RECORD_SIZE)
        struct.pack_into("<4sBBB", buf, 0, MAGIC, VERSION, (int(recipe.slot[1:]) if recipe.slot else 0), recipe.film_simulation)
        # offset 4 version already? let's restructure: magic 4, version 1 at 4
        # redo cleanly
        buf = bytearray(RECORD_SIZE)
        struct.pack_into("<4s", buf, 0, MAGIC)
        buf[4] = VERSION
        buf[5] = (int(recipe.slot[1:]) if recipe.slot else 0)
        buf[6] = recipe.film_simulation
        buf[7] = dr_code
        buf[8] = recipe.wb_mode
        struct.pack_into("<H", buf, 10, recipe.wb_kelvin)
        buf[12] = recipe.wb_shift_r & 0xFF
        buf[13] = recipe.wb_shift_b & 0xFF
        buf[14] = recipe.highlight & 0xFF
        buf[15] = recipe.shadow & 0xFF
        buf[16] = recipe.color & 0xFF
        buf[17] = recipe.sharpness & 0xFF
        buf[18] = recipe.noise_reduction & 0xFF
        buf[20:52] = name_b
        crc = zlib.crc32(bytes(buf[:124])) & 0xFFFFFFFF
        struct.pack_into("<I", buf, 124, crc)
        return bytes(buf)

    @staticmethod
    def from_bytes(data: BytesLike) -> Recipe:
        b = _as_bytes(data)
        if len(b) != RECORD_SIZE:
            raise ValueError(f"recipe record must be {RECORD_SIZE} bytes, got {len(b)}")
        if b[:4] != MAGIC:
            raise ValueError("invalid magic: not a recipe record")
        version = b[4]
        if version != VERSION:
            raise ValueError(f"unsupported version: {version}")
        slot_n = b[5]
        slot = f"C{slot_n}" if 1 <= slot_n <= 7 else None
        film_sim = b[6]
        if film_sim not in FILM_SIM_NAMES:
            raise ValueError(f"unknown film simulation id: {film_sim}")
        dr_code = b[7]
        if dr_code not in DR_VALUES:
            raise ValueError(f"unknown dynamic range code: {dr_code}")
        wb_mode = b[8]
        if wb_mode not in WB_MODE_NAMES:
            raise ValueError(f"unknown wb mode: {wb_mode}")
        wb_kelvin = struct.unpack_from("<H", b, 10)[0]
        if not (2500 <= wb_kelvin <= 10000):
            raise ValueError(f"wb_kelvin out of range: {wb_kelvin}")
        def s8(off):
            v = b[off]
            return v - 256 if v > 127 else v
        wb_shift_r = s8(12)
        wb_shift_b = s8(13)
        highlight = s8(14)
        shadow = s8(15)
        color = s8(16)
        sharpness = s8(17)
        nr = s8(18)
        name_raw = b[20:52]
        name = name_raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
        if not name:
            name = "Custom"
        stored_crc = struct.unpack_from("<I", b, 124)[0]
        calc_crc = zlib.crc32(b[:124]) & 0xFFFFFFFF
        if stored_crc != calc_crc:
            raise ValueError("checksum mismatch: corrupted record")
        # range checks
        for v, attr in ((wb_shift_r, "wb_shift_r"), (wb_shift_b, "wb_shift_b")):
            if not (-9 <= v <= 9):
                raise ValueError(f"{attr} out of range: {v}")
        for v, attr in ((highlight, "highlight"), (shadow, "shadow"), (color, "color"),
                        (sharpness, "sharpness"), (nr, "noise_reduction")):
            if not (-2 <= v <= 2):
                raise ValueError(f"{attr} out of range: {v}")
        return Recipe(
            name=name,
            slot=slot,
            film_simulation=film_sim,
            dynamic_range=DR_VALUES[dr_code],
            wb_mode=wb_mode,
            wb_kelvin=wb_kelvin,
            wb_shift_r=wb_shift_r,
            wb_shift_b=wb_shift_b,
            highlight=highlight,
            shadow=shadow,
            color=color,
            sharpness=sharpness,
            noise_reduction=nr,
        )

    @staticmethod
    def to_text(recipe: Recipe) -> str:
        RecipeSerializer._validate_recipe(recipe)
        lines = []
        lines.append("[Recipe]")
        lines.append(f"name = {recipe.name}")
        if recipe.slot:
            lines.append(f"slot = {recipe.slot}")
        lines.append(f"film_simulation = {recipe.film_simulation}  # {recipe.film_simulation_name}")
        lines.append(f"dynamic_range = {recipe.dynamic_range}")
        lines.append(f"wb_mode = {recipe.wb_mode}  # {recipe.wb_mode_name}")
        lines.append(f"wb_kelvin = {recipe.wb_kelvin}")
        lines.append(f"wb_shift_r = {recipe.wb_shift_r}")
        lines.append(f"wb_shift_b = {recipe.wb_shift_b}")
        lines.append(f"highlight = {recipe.highlight}")
        lines.append(f"shadow = {recipe.shadow}")
        lines.append(f"color = {recipe.color}")
        lines.append(f"sharpness = {recipe.sharpness}")
        lines.append(f"noise_reduction = {recipe.noise_reduction}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def from_text(text: Union[str, bytes]) -> Recipe:
        if isinstance(text, (bytes, bytearray, memoryview)):
            text = text.decode("utf-8")
        cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
        # support no section
        if "[Recipe]" not in text and "[recipe]" not in text.lower():
            text = "[Recipe]\n" + text
        cp.read_string(text)
        sec = "Recipe" if cp.has_section("Recipe") else (cp.sections()[0] if cp.sections() else None)
        if sec is None:
            raise ValueError("no section found")
        d = dict(cp[sec])

        def get(*keys, default=None, cast=None):
            for k in keys:
                for kk, vv in d.items():
                    if kk.strip().lower().replace("-", "_") == k:
                        val = vv.strip()
                        if cast:
                            try:
                                return cast(val)
                            except Exception:
                                return val
                        return val
            return default

        name = get("name", "recipe_name", "title", default="Custom")
        slot_raw = get("slot", "slot_id", default=None)
        slot = slot_raw if slot_raw not in (None, "", "none", "None") else None
        fs = get("film_simulation", "film_sim", "simulation", "film", default=0)
        try:
            fs = int(fs)
        except ValueError:
            pass
        dr = get("dynamic_range", "dr", default=100, cast=int)
        wb_mode = get("wb_mode", "white_balance", "wb", "wb_mode_id", default=0)
        try:
            wb_mode = int(wb_mode)
        except ValueError:
            pass
        kelvin = get("wb_kelvin", "kelvin", "temperature", "wb_temperature", default=5500, cast=int)
        sr = get("wb_shift_r", "shift_r", "r_shift", "wb_r", default=0, cast=int)
        sb = get("wb_shift_b", "shift_b", "b_shift", "wb_b", default=0, cast=int)
        hl = get("highlight", "highlight_tone", default=0, cast=int)
        sh = get("shadow", "shadow_tone", default=0, cast=int)
        col = get("color", "colour", "saturation", default=0, cast=int)
        sharp = get("sharpness", default=0, cast=int)
        nr = get("noise_reduction", "nr", "noise", default=0, cast=int)
        return Recipe(
            name=name,
            slot=slot,
            film_simulation=fs,
            dynamic_range=dr,
            wb_mode=wb_mode,
            wb_kelvin=kelvin,
            wb_shift_r=sr,
            wb_shift_b=sb,
            highlight=hl,
            shadow=sh,
            color=col,
            sharpness=sharp,
            noise_reduction=nr,
        )

    @staticmethod
    def to_file(recipe, path):
        Path(path).write_text(RecipeSerializer.to_text(recipe), encoding="utf-8")

    @staticmethod
    def from_file(path):
        return RecipeSerializer.from_text(Path(path).read_text(encoding="utf-8"))

    # aliases
    serialize = to_bytes
    deserialize = from_bytes
    pack = to_bytes
    unpack = from_bytes
    dump = to_bytes
    load = from_bytes
    to_binary = to_bytes
    from_binary = from_bytes
    to_string = to_text
    from_string = from_text
    parse = from_text
    parse_text = from_text
    dumps = to_text
    loads = from_text
    validate = staticmethod(lambda data: RecipeSerializer.from_bytes(data) is not None)

    @staticmethod
    def is_valid(data):
        try:
            RecipeSerializer.from_bytes(data)
            return True
        except Exception:
            return False


class RecipeBank:
    SLOTS = SLOT_NAMES

    def __init__(self, recipes: Optional[Dict[str, Recipe]] = None):
        self._slots: Dict[str, Optional[Recipe]] = {s: None for s in SLOT_NAMES}
        if recipes:
            for k, v in recipes.items():
                self.set_slot(k, v)

    def set_slot(self, slot, recipe):
        key = _norm_slot(slot)
        if not isinstance(recipe, Recipe):
            raise TypeError("recipe must be Recipe")
        recipe.slot = key
        self._slots[key] = recipe
        return recipe

    def get_slot(self, slot):
        return self._slots[_norm_slot(slot)]

    def delete_slot(self, slot):
        self._slots[_norm_slot(slot)] = None

    def clear_slot(self, slot):
        self.delete_slot(slot)

    def all_slots(self) -> Dict[str, Optional[Recipe]]:
        return dict(self._slots)

    def slots(self):
        return self.all_slots()

    def list_slots(self):
        return list(self._slots.keys())

    def filled_slots(self):
        return {k: v for k, v in self._slots.items() if v is not None}

    def export_sd(self, base_dir) -> Path:
        base = Path(base_dir)
        out_dir = base / "DCIM" / "RECIPES"
        out_dir.mkdir(parents=True, exist_ok=True)
        for slot, rec in self._slots.items():
            if rec is None:
                continue
            rec.slot = slot
            fname = f"{slot}.fujirecipe"
            (out_dir / fname).write_text(RecipeSerializer.to_text(rec), encoding="utf-8")
            # also binary
            (out_dir / f"{slot}.bin").write_bytes(RecipeSerializer.to_bytes(rec))
        return out_dir

    def import_sd(self, base_dir) -> int:
        base = Path(base_dir)
        in_dir = base / "DCIM" / "RECIPES"
        if not in_dir.exists():
            # maybe direct
            in_dir = base
        count = 0
        for p in sorted(in_dir.glob("*.fujirecipe")) + sorted(in_dir.glob("*.ini")):
            try:
                rec = RecipeSerializer.from_text(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            # infer slot from filename
            slot = p.stem
            try:
                slot = _norm_slot(slot)
            except Exception:
                slot = None
            if slot is None:
                # assign first empty
                for s in SLOT_NAMES:
                    if self._slots[s] is None:
                        slot = s
                        break
            if slot is None:
                continue
            rec.slot = slot
            self._slots[slot] = rec
            count += 1
        # binary files
        for p in sorted(in_dir.glob("*.bin")):
            try:
                rec = RecipeSerializer.from_bytes(p.read_bytes())
            except Exception:
                continue
            slot = p.stem
            try:
                slot = _norm_slot(slot)
            except Exception:
                slot = None
            if slot is None:
                for s in SLOT_NAMES:
                    if self._slots[s] is None:
                        slot = s
                        break
            if slot is None:
                continue
            rec.slot = slot
            self._slots[slot] = rec
            count += 1
        return count
    def load_builtin_recipes(self) -> None:
        """Load slots C1 through C7 with curated modern film recipes."""
        for slot, recipe in BUILTIN_RECIPES.items():
            self.set_slot(slot, recipe)

    # aliases
    save_slot = set_slot
    load_slot = get_slot
    add = set_slot
    put = set_slot
    remove = delete_slot
    export_to_sd = export_sd
    export_to_sd_card = export_sd
    import_from_sd = import_sd
    import_from_sd_card = import_sd
    export = export_sd
    import_recipes = import_sd
    to_dict = all_slots

    def __getitem__(self, slot):
        return self.get_slot(slot)

    def __setitem__(self, slot, recipe):
        self.set_slot(slot, recipe)


BUILTIN_RECIPES: Dict[str, Recipe] = {
    "C1": Recipe(
        name="Kodachrome 64", slot="C1", film_simulation="Classic Chrome",
        dynamic_range=400, wb_mode="auto", wb_shift_r=2, wb_shift_b=-4,
        highlight=-1, shadow=1, color=1, sharpness=1, noise_reduction=-2,
    ),
    "C2": Recipe(
        name="Portra 400", slot="C2", film_simulation="Classic Chrome",
        dynamic_range=400, wb_mode="auto", wb_shift_r=2, wb_shift_b=-5,
        highlight=-1, shadow=-1, color=2, sharpness=-1, noise_reduction=-2,
    ),
    "C3": Recipe(
        name="CineStill 800T", slot="C3", film_simulation="Pro Neg. Std",
        dynamic_range=400, wb_mode="incandescent", wb_shift_r=3, wb_shift_b=-5,
        highlight=0, shadow=1, color=2, sharpness=1, noise_reduction=-2,
    ),
    "C4": Recipe(
        name="Tri-X 400", slot="C4", film_simulation="Monochrome",
        dynamic_range=400, wb_mode="auto", wb_shift_r=0, wb_shift_b=0,
        highlight=2, shadow=2, color=0, sharpness=1, noise_reduction=-2,
    ),
    "C5": Recipe(
        name="Fuji Superia 400", slot="C5", film_simulation="Pro Neg. Hi",
        dynamic_range=200, wb_mode="daylight", wb_shift_r=1, wb_shift_b=-3,
        highlight=0, shadow=1, color=2, sharpness=1, noise_reduction=-2,
    ),
    "C6": Recipe(
        name="Ilford HP5 Plus", slot="C6", film_simulation="Monochrome",
        dynamic_range=400, wb_mode="auto", wb_shift_r=0, wb_shift_b=0,
        highlight=1, shadow=2, color=0, sharpness=0, noise_reduction=-2,
    ),
    "C7": Recipe(
        name="Velvia Landscape", slot="C7", film_simulation="Velvia",
        dynamic_range=100, wb_mode="daylight", wb_shift_r=1, wb_shift_b=-1,
        highlight=1, shadow=1, color=2, sharpness=2, noise_reduction=-2,
    ),
}
