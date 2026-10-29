"""Fujifilm ``.FP1`` XML profile interchange (X RAW STUDIO format).

Parses and generates the XML-based ``.FP1`` profile files used by FUJIFILM
X RAW STUDIO to exchange conversion settings (film simulation, dynamic range,
white balance, tone curves, colour, sharpness, noise reduction, grain).

Older bodies such as the X-T10 are not supported by X RAW STUDIO; this module
lets recipes cross that boundary in both directions.

Failure mitigation:
  * Volatile/PTP RAM recovery (parsing operates on in-memory text only, never
    flash): docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
  * Firmware repacking/patching recovery:
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Optional, Union

from core.recipe import Recipe, FILM_SIM_NAMES, WB_MODE_NAMES, WB_MODES, DR_CODES, DR_VALUES

BytesLike = Union[bytes, bytearray, str, Path]

_FP1_FILM_SIM: Dict[str, int] = {
    name.strip().lower(): fid for fid, name in FILM_SIM_NAMES.items()
}

_FP1_WB: Dict[str, int] = {
    "auto": 0,
    "daylight": 1,
    "shade": 2,
    "fluorescent": 3,
    "incandescent": 6,
    "underwater": 7,
    "kelvin": 8,
}

_FP1_WB_REVERSE: Dict[int, str] = {
    0: "Auto", 1: "Daylight", 2: "Shade", 3: "Fluorescent",
    6: "Incandescent", 7: "Underwater", 8: "Kelvin",
}

_GRAIN_REVERSE: Dict[int, str] = {0: "Off", 1: "Weak", 2: "Strong"}


def _as_text(inp: Any) -> str:
    if isinstance(inp, (bytes, bytearray)):
        return bytes(inp).decode("utf-8", "replace")
    if isinstance(inp, Path):
        return inp.read_text(encoding="utf-8")
    if isinstance(inp, str):
        p = Path(inp)
        if p.exists() and p.is_file():
            try:
                return p.read_text(encoding="utf-8")
            except OSError:
                pass
        return inp
    return str(inp)


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _find_text(root: ET.Element, tag: str) -> Optional[str]:
    for el in root.iter():
        if _local(el.tag).lower() == tag.lower():
            if el.text is not None:
                t = el.text.strip()
                if t != "":
                    return t
    return None


def _to_int(val: Optional[str]) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


class FP1Converter:
    """Parse and generate Fujifilm ``.FP1`` XML profiles."""

    @staticmethod
    def to_recipe(fp1_text_or_path: Any) -> Recipe:
        """Convert ``.FP1`` XML text or file path to a :class:`Recipe`."""
        text = _as_text(fp1_text_or_path)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ValueError(f"invalid FP1 XML: {exc}") from exc

        kwargs: Dict[str, Any] = {}

        # Film simulation
        fs = _find_text(root, "FilmSimulation")
        if fs is not None:
            key = fs.strip().lower()
            if key in _FP1_FILM_SIM:
                kwargs["film_simulation"] = _FP1_FILM_SIM[key]

        # Dynamic range
        dr = _find_text(root, "DynamicRange")
        if dr is not None:
            key = dr.strip().upper().replace(" ", "")
            if key.startswith("DR"):
                try:
                    n = int(key[2:])
                    if n in (100, 200, 400):
                        kwargs["dynamic_range"] = n
                except ValueError:
                    pass
            else:
                try:
                    n = int(dr)
                    if n in (100, 200, 400):
                        kwargs["dynamic_range"] = n
                except ValueError:
                    pass

        # White balance
        wb = _find_text(root, "WhiteBalance")
        if wb is not None:
            key = wb.strip().lower()
            if key in _FP1_WB:
                kwargs["wb_mode"] = _FP1_WB[key]

        # Color temperature
        ct = _to_int(_find_text(root, "ColorTemperature"))
        if ct is not None and 2500 <= ct <= 10000:
            kwargs["wb_kelvin"] = ct

        # WB shifts
        for tag, attr in (("WBShiftR", "wb_shift_r"), ("WBShiftB", "wb_shift_b")):
            v = _to_int(_find_text(root, tag))
            if v is not None and -9 <= v <= 9:
                kwargs[attr] = v

        # Tone
        for tag, attr, lo, hi in (
            ("HighlightTone", "highlight", -2, 4),
            ("ShadowTone", "shadow", -2, 4),
        ):
            v = _to_int(_find_text(root, tag))
            if v is not None and lo <= v <= hi:
                kwargs[attr] = v

        # Color / sharpness / NR
        for tag, attr, lo, hi in (
            ("Color", "color", -4, 4),
            ("Sharpness", "sharpness", -4, 4),
            ("NoiseReduction", "noise_reduction", -4, 4),
        ):
            v = _to_int(_find_text(root, tag))
            if v is not None and lo <= v <= hi:
                kwargs[attr] = v

        # Name (optional)
        name = _find_text(root, "Name") or _find_text(root, "ProfileName")
        if name is not None:
            kwargs["name"] = name

        try:
            return Recipe(**kwargs)
        except (ValueError, TypeError):
            # Fall back to defaults if something unexpected slipped through.
            safe = {}
            for k, v in kwargs.items():
                try:
                    Recipe(**{k: v})
                    safe[k] = v
                except (ValueError, TypeError):
                    continue
            return Recipe(**safe)

    @staticmethod
    def from_recipe(recipe: Any, camera_model: str = "X-T10") -> str:
        """Generate valid ``.FP1`` XML from a :class:`Recipe`."""
        if not isinstance(recipe, Recipe):
            if isinstance(recipe, dict):
                recipe = Recipe.from_dict(recipe)
            else:
                recipe = Recipe(**recipe) if hasattr(recipe, "__dict__") else Recipe()

        fs_name = FILM_SIM_NAMES.get(recipe.film_simulation, "Provia")
        dr_str = f"DR{recipe.dynamic_range}"
        wb_name = _FP1_WB_REVERSE.get(recipe.wb_mode, "Auto")

        lines = []
        lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        lines.append(f'<Profile CameraModel="{camera_model}">')
        lines.append(f"  <FilmSimulation>{fs_name}</FilmSimulation>")
        lines.append(f"  <DynamicRange>{dr_str}</DynamicRange>")
        lines.append(f"  <WhiteBalance>{wb_name}</WhiteBalance>")
        lines.append(f"  <ColorTemperature>{recipe.wb_kelvin}</ColorTemperature>")
        lines.append(f"  <WBShiftR>{recipe.wb_shift_r}</WBShiftR>")
        lines.append(f"  <WBShiftB>{recipe.wb_shift_b}</WBShiftB>")
        lines.append(f"  <HighlightTone>{recipe.highlight}</HighlightTone>")
        lines.append(f"  <ShadowTone>{recipe.shadow}</ShadowTone>")
        lines.append(f"  <Color>{recipe.color}</Color>")
        lines.append(f"  <Sharpness>{recipe.sharpness}</Sharpness>")
        lines.append(f"  <NoiseReduction>{recipe.noise_reduction}</NoiseReduction>")
        lines.append("  <GrainEffect>Off</GrainEffect>")
        lines.append("</Profile>")
        return "\n".join(lines) + "\n"

    # Aliases
    parse = to_recipe
    load = to_recipe
    from_fp1 = to_recipe
    from_text = to_recipe
    from_file = to_recipe
    generate = from_recipe
    dump = from_recipe
    to_fp1 = from_recipe
    to_text = from_recipe
    to_string = from_recipe
    to_file = None


# Convenience module-level functions
def to_recipe(*a, **k):
    return FP1Converter.to_recipe(*a, **k)


def from_recipe(*a, **k):
    return FP1Converter.from_recipe(*a, **k)


# Remove the placeholder to avoid accidental misuse.
FP1Converter.to_file = staticmethod(
    lambda recipe, path, camera_model="X-T10": Path(path).write_text(
        FP1Converter.from_recipe(recipe, camera_model=camera_model), encoding="utf-8"
    )
)
