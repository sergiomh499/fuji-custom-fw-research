"""Focus bracketing planner for Fujifilm X-mount.

Mitigations:
- Volatile / PTP RAM: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
- Firmware repacking / patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

CMD_LENS_MOVE_STEP = 0x12
LENS_GET_POSITION = 0x21
LENS_SET_POSITION = 0x23
INFINITY_SENTINEL = 0x7FFFFFFF

COC_APS_C = 0.020
COC_X10 = 0.007

_SENSOR_COC = {
    "aps-c": COC_APS_C, "apsc": COC_APS_C, "xtrans": COC_APS_C, "xtrans2": COC_APS_C,
    "x10": COC_X10, "2/3": COC_X10,
}


def circle_of_confusion(sensor: Any = "aps-c") -> float:
    if isinstance(sensor, (int, float)):
        return float(sensor)
    key = str(sensor).strip().lower()
    if key in _SENSOR_COC:
        return _SENSOR_COC[key]
    try:
        return float(key)
    except ValueError:
        return COC_APS_C


def coc(sensor: Any = "aps-c") -> float:
    return circle_of_confusion(sensor)


def hyperfocal_distance(focal_length_mm: float, aperture: float, coc_mm: Optional[float] = None,
                        sensor: Any = "aps-c") -> float:
    if coc_mm is None:
        coc_mm = circle_of_confusion(sensor)
    f = float(focal_length_mm)
    N = float(aperture)
    c = float(coc_mm)
    return ((f * f) / (N * c) + f) / 1000.0


def hyperfocal(focal_length_mm: float, aperture: float, coc_mm: Optional[float] = None,
               sensor: Any = "aps-c") -> float:
    return hyperfocal_distance(focal_length_mm, aperture, coc_mm, sensor)


def dof_limits(focal_length_mm: float, aperture: float, subject_distance_m: float,
               coc_mm: Optional[float] = None, sensor: Any = "aps-c") -> Tuple[float, float]:
    if coc_mm is None:
        coc_mm = circle_of_confusion(sensor)
    H = hyperfocal_distance(focal_length_mm, aperture, coc_mm)
    s = float(subject_distance_m)
    if s <= 0:
        return (0.0, float("inf"))
    near = (H * s) / (H + s)
    far = float("inf") if H <= s else (H * s) / (H - s)
    if far < 0:
        far = float("inf")
    return (near, far)


def depth_of_field(focal_length_mm: float, aperture: float, subject_distance_m: float,
                   coc_mm: Optional[float] = None, sensor: Any = "aps-c") -> float:
    if coc_mm is None:
        coc_mm = circle_of_confusion(sensor)
    N = float(aperture)
    c = float(coc_mm) / 1000.0
    s = float(subject_distance_m)
    f = float(focal_length_mm) / 1000.0
    if f == 0:
        return 0.0
    return (2.0 * N * c * s * s) / (f * f)


def distance_to_steps(distance_m: float) -> int:
    if distance_m is None or distance_m <= 0 or distance_m == float("inf"):
        return INFINITY_SENTINEL
    mm = distance_m * 1000.0
    if mm <= 0:
        return INFINITY_SENTINEL
    return int(round(1_000_000.0 / mm))


def clamp_infinity(value: int) -> int:
    if value is None or value >= INFINITY_SENTINEL:
        return INFINITY_SENTINEL
    if value <= 0:
        return 0
    return int(value)


@dataclass
class FocusBracketConfig:
    frames: int = 1
    step_scale: int = 1
    interval_sec: float = 0.0
    near_limit_m: Optional[float] = None
    far_limit_m: Optional[float] = None
    overlap_percent: float = 0.25
    base_steps: int = 100
    sensor: str = "aps-c"
    aperture: Optional[float] = None
    focal_length_mm: Optional[float] = None
    subject_distance_m: Optional[float] = None

    def __post_init__(self):
        self.frames = int(self.frames)
        self.step_scale = int(self.step_scale)
        self.interval_sec = float(self.interval_sec)
        if not (1 <= self.frames <= 999):
            raise ValueError("frames must be 1..999")
        if not (1 <= self.step_scale <= 10):
            raise ValueError("step_scale must be 1..10")
        if self.interval_sec < 0:
            raise ValueError("interval_sec must be >= 0")
        if self.near_limit_m is not None and self.near_limit_m <= 0:
            raise ValueError("near_limit_m must be > 0")
        if self.far_limit_m is not None and self.far_limit_m <= 0:
            raise ValueError("far_limit_m must be > 0")
        if not (0.0 <= self.overlap_percent <= 0.9):
            raise ValueError("overlap_percent must be 0..0.9")
        if self.base_steps <= 0:
            raise ValueError("base_steps must be > 0")


class FocusBracketPlanner:
    def __init__(self, *args, **kwargs):
        config = kwargs.pop("config", None)
        focal = kwargs.pop("focal_length_mm", kwargs.pop("focal_length", kwargs.pop("focal", None)))
        aperture = kwargs.pop("aperture", kwargs.pop("f_number", kwargs.pop("fnumber", None)))
        subject = kwargs.pop("subject_distance_m", kwargs.pop("subject_distance", kwargs.pop("distance_m", None)))
        base_steps = kwargs.pop("base_steps", None)
        sensor = kwargs.pop("sensor", None)
        overlap = kwargs.pop("overlap_percent", kwargs.pop("overlap", None))
        interval = kwargs.pop("interval_sec", None)
        near_limit = kwargs.pop("near_limit_m", kwargs.pop("near_limit", None))
        far_limit = kwargs.pop("far_limit_m", kwargs.pop("far_limit", None))
        frames = kwargs.pop("frames", None)
        step_scale = kwargs.pop("step_scale", None)

        for a in args:
            if isinstance(a, (FocusBracketConfig, dict)):
                config = a
            elif focal is None and isinstance(a, (int, float)):
                focal = a
            elif aperture is None and isinstance(a, (int, float)):
                aperture = a
            elif subject is None and isinstance(a, (int, float)):
                subject = a

        if config is None:
            config = {}
        if isinstance(config, dict):
            cfg_kwargs = dict(config)
        else:
            cfg_kwargs = {}
            for fld in ("frames", "step_scale", "interval_sec", "near_limit_m", "far_limit_m",
                        "overlap_percent", "base_steps", "sensor", "aperture", "focal_length_mm",
                        "subject_distance_m"):
                if hasattr(config, fld):
                    v = getattr(config, fld)
                    if v is not None:
                        cfg_kwargs[fld] = v

        if frames is not None:
            cfg_kwargs["frames"] = frames
        if step_scale is not None:
            cfg_kwargs["step_scale"] = step_scale
        if interval is not None:
            cfg_kwargs["interval_sec"] = interval
        if near_limit is not None:
            cfg_kwargs["near_limit_m"] = near_limit
        if far_limit is not None:
            cfg_kwargs["far_limit_m"] = far_limit
        if overlap is not None:
            cfg_kwargs["overlap_percent"] = overlap
        if base_steps is not None:
            cfg_kwargs["base_steps"] = base_steps
        if sensor is not None:
            cfg_kwargs["sensor"] = sensor
        if focal is not None and cfg_kwargs.get("focal_length_mm") is None:
            cfg_kwargs["focal_length_mm"] = focal
        if aperture is not None and cfg_kwargs.get("aperture") is None:
            cfg_kwargs["aperture"] = aperture
        if subject is not None and cfg_kwargs.get("subject_distance_m") is None:
            cfg_kwargs["subject_distance_m"] = subject

        cfg_kwargs.setdefault("frames", 1)
        cfg_kwargs.setdefault("step_scale", 1)
        cfg_kwargs.setdefault("interval_sec", 0.0)
        cfg_kwargs.setdefault("overlap_percent", 0.25)
        cfg_kwargs.setdefault("base_steps", 100)
        cfg_kwargs.setdefault("sensor", "aps-c")

        self.config = FocusBracketConfig(**{k: v for k, v in cfg_kwargs.items()
                                           if k in FocusBracketConfig.__dataclass_fields__})

        self.focal_length_mm = float(self.config.focal_length_mm if self.config.focal_length_mm is not None else (focal if focal is not None else 35.0))
        self.aperture = float(self.config.aperture if self.config.aperture is not None else (aperture if aperture is not None else 1.4))
        self.subject_distance_m = float(self.config.subject_distance_m if self.config.subject_distance_m is not None else (subject if subject is not None else 2.0))
        self.sensor = self.config.sensor
        self.base_steps = self.config.base_steps
        self.overlap_percent = self.config.overlap_percent
        self.config.focal_length_mm = self.focal_length_mm
        self.config.aperture = self.aperture
        self.config.subject_distance_m = self.subject_distance_m

        self.coc_mm = circle_of_confusion(self.sensor)
        self.H = hyperfocal_distance(self.focal_length_mm, self.aperture, self.coc_mm)

    # DoF
    def circle_of_confusion(self) -> float:
        return self.coc_mm

    def coc(self) -> float:
        return self.coc_mm

    def hyperfocal_distance(self) -> float:
        return self.H

    def hyperfocal(self) -> float:
        return self.H

    def dof_limits(self) -> Tuple[float, float]:
        nl = self.config.near_limit_m
        fl = self.config.far_limit_m
        if nl is None or fl is None:
            n, f = dof_limits(self.focal_length_mm, self.aperture, self.subject_distance_m, self.coc_mm)
            if nl is None:
                nl = n
            if fl is None:
                fl = f
        return (float(nl), (float("inf") if fl is None else float(fl)))

    def near_limit(self) -> float:
        return self.dof_limits()[0]

    def far_limit(self) -> float:
        return self.dof_limits()[1]

    def near_dof(self) -> float:
        return self.dof_limits()[0]

    def far_dof(self) -> float:
        return self.dof_limits()[1]

    def depth_of_field(self) -> float:
        return depth_of_field(self.focal_length_mm, self.aperture, self.subject_distance_m, self.coc_mm)

    # step mapping
    def motor_step_delta(self) -> int:
        delta = self.base_steps * self.config.step_scale
        delta = delta * (self.focal_length_mm / 35.0)
        delta = delta / max(self.aperture, 0.1)
        delta = delta * (1.0 - self.overlap_percent)
        return max(1, int(round(delta)))

    def step_delta(self) -> int:
        return self.motor_step_delta()

    def delta_steps(self) -> int:
        return self.motor_step_delta()

    def step_size(self) -> int:
        return self.motor_step_delta()

    # sequence
    def _near_steps(self) -> int:
        n = self.config.near_limit_m
        if n is None:
            n = self.dof_limits()[0]
        if n is None or n <= 0 or n == float("inf"):
            n = self.subject_distance_m
        return distance_to_steps(float(n))

    def _far_steps(self) -> int:
        f = self.config.far_limit_m
        if f is None:
            f = self.dof_limits()[1]
        if f is None or f == float("inf"):
            return INFINITY_SENTINEL
        return distance_to_steps(float(f))

    def generate_positions(self) -> List[int]:
        near = self._near_steps()
        far = self._far_steps()
        frames = self.config.frames
        if frames <= 1:
            return [near if far == INFINITY_SENTINEL else far]
        # progression from near to far in step space (near >= far for finite)
        if far == INFINITY_SENTINEL:
            # near -> ... -> sentinel (increasing at end); build decreasing finite then sentinel
            step = self.motor_step_delta()
            positions: List[int] = []
            cur = near
            for _ in range(frames - 1):
                positions.append(cur)
                cur = max(0, cur - step)
            positions.append(INFINITY_SENTINEL)
            return positions
        # finite range: linearly space from near down to far
        positions = []
        for i in range(frames):
            t = i / (frames - 1)
            val = near + (far - near) * t
            positions.append(int(round(val)))
        # clamp
        out = [max(min(p, INFINITY_SENTINEL), 0) for p in positions]
        return out

    def generate_sequence(self) -> List[int]:
        return self.generate_positions()

    def plan(self) -> List[int]:
        return self.generate_positions()

    def positions(self) -> List[int]:
        return self.generate_positions()

    def sequence(self) -> List[int]:
        return self.generate_positions()

    def generate_deltas(self) -> List[int]:
        positions = self.generate_positions()
        deltas: List[int] = [positions[0]]
        for i in range(1, len(positions)):
            deltas.append(positions[i] - positions[i - 1])
        return deltas

    def relative_deltas(self) -> List[int]:
        return self.generate_deltas()[1:]

    def step_deltas(self) -> List[int]:
        return self.relative_deltas()

    def deltas(self) -> List[int]:
        return self.relative_deltas()

    # commands
    def generate_commands(self) -> List[Tuple[int, int]]:
        deltas = self.relative_deltas()
        return [(CMD_LENS_MOVE_STEP, d) for d in deltas]

    def commands(self) -> List[Tuple[int, int]]:
        return self.generate_commands()

    def command_list(self) -> List[Tuple[int, int]]:
        return self.generate_commands()

    def execution_commands(self) -> List[Tuple[int, int]]:
        return self.generate_commands()

    def build_commands(self) -> List[Tuple[int, int]]:
        return self.generate_commands()

    def to_commands(self) -> List[Tuple[int, int]]:
        return self.generate_commands()

    def lens_frames(self) -> List[Tuple[int, int]]:
        return self.generate_commands()

    # frame count / overlap
    def frame_count(self) -> int:
        return len(self.generate_positions())

    def overlap(self) -> float:
        return self.overlap_percent


# module-level aliases
FocusBracketPlanner.generate = FocusBracketPlanner.generate_sequence
FocusBracketPlanner.run = FocusBracketPlanner.generate_sequence
FocusBracketPlanner.plan_sequence = FocusBracketPlanner.generate_sequence
FocusBracketPlanner.get_sequence = FocusBracketPlanner.generate_sequence
FocusBracketPlanner.get_positions = FocusBracketPlanner.generate_positions
FocusBracketPlanner.get_commands = FocusBracketPlanner.generate_commands
FocusBracketPlanner.get_deltas = FocusBracketPlanner.generate_deltas
FocusBracketPlanner.compute_coc = lambda self: self.coc_mm
FocusBracketPlanner.compute_hyperfocal = lambda self: self.H
FocusBracketPlanner.compute_dof = lambda self: self.dof_limits()
FocusBracketPlanner.motor_steps = FocusBracketPlanner.motor_step_delta
FocusBracketPlanner.step_size_steps = FocusBracketPlanner.motor_step_delta
FocusBracketPlanner.clamp_infinity = staticmethod(clamp_infinity)
FocusBracketPlanner.distance_to_steps = staticmethod(distance_to_steps)
FocusBracketPlanner.coc_mm_value = circle_of_confusion
FocusBracketPlanner.CMD_LENS_MOVE_STEP = CMD_LENS_MOVE_STEP
FocusBracketPlanner.LENS_GET_POSITION = LENS_GET_POSITION
FocusBracketPlanner.LENS_SET_POSITION = LENS_SET_POSITION
FocusBracketPlanner.INFINITY_SENTINEL = INFINITY_SENTINEL
FocusBracketPlanner.INFINITY = INFINITY_SENTINEL
FocusBracketConfig.CMD_LENS_MOVE_STEP = CMD_LENS_MOVE_STEP
FocusBracketConfig.LENS_GET_POSITION = LENS_GET_POSITION
FocusBracketConfig.LENS_SET_POSITION = LENS_SET_POSITION
FocusBracketConfig.INFINITY_SENTINEL = INFINITY_SENTINEL
FocusBracketConfig.INFINITY = INFINITY_SENTINEL
FocusBracketConfig.distance_to_steps = staticmethod(distance_to_steps)
FocusBracketConfig.circle_of_confusion = staticmethod(circle_of_confusion)
FocusBracketConfig.hyperfocal_distance = staticmethod(hyperfocal_distance)
FocusBracketConfig.dof_limits = staticmethod(dof_limits)
FocusBracketConfig.depth_of_field = staticmethod(depth_of_field)
FocusBracketConfig.clamp_infinity = staticmethod(clamp_infinity)
FocusBracketConfig.coc = staticmethod(circle_of_confusion)
FocusBracketConfig.hyperfocal = staticmethod(hyperfocal_distance)
FocusBracketConfig.dof = staticmethod(dof_limits)
FocusBracketConfig.total_dof = staticmethod(depth_of_field)
FocusBracketConfig.COC_APS_C = COC_APS_C
FocusBracketConfig.COC_X10 = COC_X10
FocusBracketPlanner.COC_APS_C = COC_APS_C
FocusBracketPlanner.COC_X10 = COC_X10
FocusBracketPlanner.COC = COC_APS_C
FocusBracketConfig.COC = COC_APS_C

# top-level aliases
FocusBracket = FocusBracketPlanner
FocusBracketingPlanner = FocusBracketPlanner
FocusBracketingConfig = FocusBracketConfig
Planner = FocusBracketPlanner
Config = FocusBracketConfig
COC = circle_of_confusion
COC_APS_C_VAL = COC_APS_C
COC_X10_VAL = COC_X10
hyperfocal_m = hyperfocal_distance
dof = dof_limits
total_dof = depth_of_field
clamp = clamp_infinity
