"""Auto ISO slot management and dynamic min-shutter calculation.

Reverse-engineered / ported from modern Fujifilm bodies into the X-T10 research
framework (no flashing required; pure host-side model).

Auto ISO presents three customizable slots (AUTO 1/2/3). Each slot stores a
default (base) sensitivity, a maximum sensitivity, and a minimum shutter speed
policy: either a fixed fractional time or an "AUTO" dynamic policy derived from
the attached lens focal length (X-mount CMD_LENS_INFO 0x40).

Dynamic ("AUTO") policy (1 / equivalent focal length), with EV shift:
  * Standard: 1 / (1 * eq_focal)
  * Fast (+1 EV): 1 / (2 * eq_focal)
  * Faster (+2 EV): 1 / (4 * eq_focal)
  * Slow (-1 EV): 1 / (0.5 * eq_focal)
  * Slower (-2 EV): 1 / (0.25 * eq_focal)
  eq_focal = focal_length_mm * crop_factor (1.5x X-T10, 3.93x X10 2/3").

Failure mitigation:
  * Volatile / PTP RAM only: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
  * Firmware repacking / patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

CROP_XT10 = 1.5
CROP_X10 = 3.93

# Standard photographic shutter speeds (seconds), 1/3-stop-ish progression.
STANDARD_SHUTTERS: List[float] = [
    1 / 30, 1 / 40, 1 / 50, 1 / 60, 1 / 80, 1 / 100, 1 / 125, 1 / 160,
    1 / 200, 1 / 250, 1 / 320, 1 / 400, 1 / 500, 1 / 640, 1 / 800,
    1 / 1000, 1 / 1250, 1 / 1600, 1 / 2000, 1 / 2500, 1 / 3200, 1 / 4000,
    1 / 5000, 1 / 6400, 1 / 8000,
]

SHIFT_MULTIPLIERS: Dict[str, float] = {
    "standard": 1.0,
    "fast": 2.0,
    "+1": 2.0,
    "faster": 4.0,
    "+2": 4.0,
    "slow": 0.5,
    "-1": 0.5,
    "slower": 0.25,
    "-2": 0.25,
}

SLOT_IDS = ("AUTO1", "AUTO2", "AUTO3")


def _norm_shift(value: Any) -> str:
    s = str(value).strip().lower()
    # strip EV annotations
    s = s.replace("(+1 ev)", "").replace("(+2 ev)", "").replace("(-1 ev)", "").replace("(-2 ev)", "")
    s = s.strip()
    key = s.replace(" ", "").replace("_", "")
    # map common variants
    mapping = {
        "standard": "standard",
        "std": "standard",
        "fast": "fast",
        "fast+1": "fast",
        "faster": "faster",
        "fast+2": "faster",
        "slow": "slow",
        "slower": "slower",
    }
    if key in mapping:
        return mapping[key]
    if key in SHIFT_MULTIPLIERS:
        return key
    # fallback: substring
    for k in ("faster", "fast", "slower", "slow", "standard"):
        if k in key:
            return k
    return "standard"


def _parse_fraction(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v if v > 0 else None
    s = str(value).strip().upper()
    if s in ("AUTO", "DYNAMIC", ""):
        return None
    if "/" in s:
        num, den = s.split("/", 1)
        try:
            return float(num) / float(den)
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def quantize_shutter(seconds: float) -> float:
    """Round a shutter time (seconds) to the nearest standard stop."""
    seconds = float(seconds)
    if seconds <= 0:
        return STANDARD_SHUTTERS[0]
    return min(STANDARD_SHUTTERS, key=lambda s: abs(s - seconds))


def shutter_string(seconds: float) -> str:
    """Render a shutter time as '1/N' (best-effort)."""
    seconds = float(seconds)
    if seconds <= 0:
        return "1/8000"
    den = int(round(1.0 / seconds))
    return f"1/{den}"


@dataclass
class AutoISOSlot:
    """One Auto ISO preset.

    Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
    """

    slot_id: str
    default_iso: int
    max_iso: int
    min_shutter_mode: str = "AUTO"
    min_shutter_seconds: Optional[float] = None
    shift_rate: str = "Standard"
    # alias fields (optional)
    shift: Optional[str] = None
    min_shutter_speed: Any = None
    min_shutter: Any = None

    def __post_init__(self):
        self.slot_id = str(self.slot_id).upper()
        # alias resolution
        if self.shift is not None:
            self.shift_rate = self.shift
        if self.min_shutter_speed is not None:
            parsed = _parse_fraction(self.min_shutter_speed)
            if parsed is None and str(self.min_shutter_speed).upper() in ("AUTO", "DYNAMIC", ""):
                self.min_shutter_mode = "AUTO"
            else:
                if parsed is not None:
                    self.min_shutter_mode = "fixed"
                    self.min_shutter_seconds = parsed
        if self.min_shutter is not None:
            parsed = _parse_fraction(self.min_shutter)
            if parsed is None and str(self.min_shutter).upper() in ("AUTO", "DYNAMIC", ""):
                self.min_shutter_mode = "AUTO"
            else:
                if parsed is not None:
                    self.min_shutter_mode = "fixed"
                    self.min_shutter_seconds = parsed
        # mode normalization
        mode_upper = str(self.min_shutter_mode).upper()
        if mode_upper in ("AUTO", "DYNAMIC"):
            self.min_shutter_mode = "AUTO"
        else:
            parsed = _parse_fraction(self.min_shutter_mode)
            if parsed is not None:
                self.min_shutter_mode = "fixed"
                if self.min_shutter_seconds is None:
                    self.min_shutter_seconds = parsed
            elif self.min_shutter_seconds is None:
                # try mode as fraction string already handled; default auto
                self.min_shutter_mode = "AUTO"
        # validate ISO
        self.default_iso = int(self.default_iso)
        self.max_iso = int(self.max_iso)
        if not (200 <= self.default_iso <= 12800):
            raise ValueError(f"default_iso out of range: {self.default_iso}")
        if not (200 <= self.max_iso <= 12800):
            raise ValueError(f"max_iso out of range: {self.max_iso}")
        if self.default_iso > self.max_iso:
            raise ValueError(f"default_iso ({self.default_iso}) > max_iso ({self.max_iso})")
        # validate shift
        self.shift_rate = _norm_shift(self.shift_rate)
        # validate fixed seconds
        if self.min_shutter_mode == "fixed":
            if self.min_shutter_seconds is None:
                parsed = _parse_fraction(mode_upper)
                if parsed is not None:
                    self.min_shutter_seconds = parsed
            if self.min_shutter_seconds is None or self.min_shutter_seconds <= 0:
                raise ValueError("fixed min shutter requires positive seconds")
            self.min_shutter_seconds = quantize_shutter(self.min_shutter_seconds)

    @property
    def is_auto(self) -> bool:
        return self.min_shutter_mode == "AUTO"


class AutoISOManager:
    """Manage AUTO1/2/3 slots and compute target min shutter speed.

    Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
    Firmware-level patching recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
    """

    def __init__(self, slots: Optional[List[AutoISOSlot]] = None):
        if slots is None:
            slots = [
                AutoISOSlot("AUTO1", 200, 3200, "AUTO", None, "Standard"),
                AutoISOSlot("AUTO2", 200, 6400, "AUTO", None, "Standard"),
                AutoISOSlot("AUTO3", 200, 12800, "AUTO", None, "Standard"),
            ]
        self.slots: Dict[str, AutoISOSlot] = {}
        for s in slots:
            self.slots[s.slot_id] = s
        self.active_slot_id: str = next(iter(self.slots)) if self.slots else "AUTO1"
        if "AUTO1" in self.slots:
            self.active_slot_id = "AUTO1"

    @property
    def active_slot(self) -> AutoISOSlot:
        return self.slots[self.active_slot_id]

    def select_slot(self, slot_id: str) -> None:
        sid = str(slot_id).upper()
        if sid not in self.slots:
            raise ValueError(f"unknown slot: {slot_id}")
        self.active_slot_id = sid

    def set_active_slot(self, slot_id: str) -> None:
        self.select_slot(slot_id)

    def get_slot(self, slot_id: Optional[str] = None) -> AutoISOSlot:
        if slot_id is None:
            return self.active_slot
        sid = str(slot_id).upper()
        if sid not in self.slots:
            raise ValueError(f"unknown slot: {slot_id}")
        return self.slots[sid]

    def add_slot(self, slot: AutoISOSlot) -> None:
        self.slots[slot.slot_id] = slot

    def shift_multiplier(self, shift: Any) -> float:
        key = _norm_shift(shift)
        return SHIFT_MULTIPLIERS.get(key, 1.0)

    def calculate_min_shutter(self, focal_length_mm: float, crop_factor: float = CROP_XT10,
                              scene_ev: Optional[float] = None, slot_id: Optional[str] = None,
                              shift_rate: Optional[str] = None) -> float:
        slot = self.get_slot(slot_id)
        if slot.min_shutter_mode == "fixed":
            return quantize_shutter(slot.min_shutter_seconds)
        shift = shift_rate if shift_rate is not None else slot.shift_rate
        mult = self.shift_multiplier(shift)
        eq = float(focal_length_mm) * float(crop_factor)
        if eq <= 0:
            raise ValueError("focal length / crop factor must be positive")
        target = 1.0 / (mult * eq)
        return quantize_shutter(target)

    # aliases
    def calculate_target_shutter(self, *a, **kw):
        return self.calculate_min_shutter(*a, **kw)

    def calculate_shutter_speed(self, *a, **kw):
        return self.calculate_min_shutter(*a, **kw)

    def target_shutter_speed(self, *a, **kw):
        return self.calculate_min_shutter(*a, **kw)

    def min_shutter_speed(self, *a, **kw):
        return self.calculate_min_shutter(*a, **kw)
