"""Intervalometer with exposure smoothing for Fujifilm X-mount research.

Modern Fujifilm bodies support advanced interval timer shooting with Auto
Exposure Smoothing for day-to-night (holy grail) timelapses. This module
models that behaviour host-side: schedule generation, scene-brightness
evaluation and micro-step exposure compensation.

Mitigations:
- Volatile / PTP RAM: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
- Firmware repacking / patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

import math


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass
class IntervalometerConfig:
    interval_sec: float = 1.0
    total_frames: int = 0  # 0 => infinite
    start_delay_sec: float = 0.0
    exposure_smoothing: bool = False
    smoothing_window: int = 5
    max_ev_step_per_frame: float = 0.1

    def __post_init__(self):
        self.interval_sec = float(self.interval_sec)
        self.total_frames = int(self.total_frames)
        self.start_delay_sec = float(self.start_delay_sec)
        self.exposure_smoothing = bool(self.exposure_smoothing)
        self.smoothing_window = int(self.smoothing_window)
        self.max_ev_step_per_frame = float(self.max_ev_step_per_frame)

        if self.interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
        if self.total_frames < 0:
            raise ValueError("total_frames must be >= 0")
        if self.start_delay_sec < 0:
            raise ValueError("start_delay_sec must be >= 0")
        if self.smoothing_window < 1:
            raise ValueError("smoothing_window must be >= 1")
        if self.max_ev_step_per_frame <= 0:
            raise ValueError("max_ev_step_per_frame must be > 0")


# aliases
IntervalConfig = IntervalometerConfig
IntervalometerCfg = IntervalometerConfig


class ExposureSmoother:
    """Tracks scene luminance and computes smoothed exposure compensation.

    Uses a rolling moving average over ``window`` samples as the baseline
    target, then derives a clamped per-frame micro-step (delta EV) so that
    frame-to-frame exposure stepping stays below perceptual thresholds.
    """

    def __init__(self, window: int = 5, max_ev_step_per_frame: float = 0.1,
                 smoothing_window: Optional[int] = None, max_step: Optional[float] = None,
                 alpha: Optional[float] = None, **kwargs):
        if smoothing_window is not None:
            window = smoothing_window
        if max_step is not None:
            max_ev_step_per_frame = max_step
        if "max_ev_step" in kwargs:
            max_ev_step_per_frame = kwargs.pop("max_ev_step")
        self.window = max(1, int(window))
        self.max_ev_step_per_frame = float(max_ev_step_per_frame)
        self.alpha = alpha
        self.history: List[float] = []
        self.applied_ev: float = 0.0
        self._last_smoothed: Optional[float] = None

    # ---- core ------------------------------------------------------------- #
    def update(self, value: float) -> Dict[str, float]:
        v = float(value)
        self.history.append(v)
        if len(self.history) > self.window:
            self.history = self.history[-self.window:]

        if self.alpha is not None:
            # optional EMA blend on top of moving average
            if self._last_smoothed is None:
                smoothed = v
            else:
                smoothed = self.alpha * v + (1.0 - self.alpha) * self._last_smoothed
        else:
            smoothed = sum(self.history) / len(self.history)

        # desired exposure compensation moves toward smoothed baseline
        desired = smoothed - v
        # clamp per-frame step
        step = max(-self.max_ev_step_per_frame,
                   min(self.max_ev_step_per_frame, desired))
        # also limit total movement toward smoothed target
        self.applied_ev += step
        self._last_smoothed = smoothed
        return {
            "raw": v,
            "smoothed": smoothed,
            "delta_ev": step,
            "applied_ev": self.applied_ev,
        }

    def observe(self, value):
        return self.update(value)

    def process(self, value):
        return self.update(value)

    def step(self, value):
        return self.update(value)

    # ---- accessors -------------------------------------------------------- #
    @property
    def smoothed_value(self) -> Optional[float]:
        if not self.history:
            return None
        return self._last_smoothed

    @property
    def baseline(self) -> Optional[float]:
        return self.smoothed_value

    @property
    def smoothed_luminance(self) -> Optional[float]:
        return self.smoothed_value

    def smoothed(self, value=None):
        if value is not None:
            return self.update(value)["smoothed"]
        return self.smoothed_value

    def delta_ev(self, value=None):
        if value is not None:
            return self.update(value)["delta_ev"]
        return 0.0

    def reset(self):
        self.history.clear()
        self.applied_ev = 0.0
        self._last_smoothed = None


# aliases
Smoother = ExposureSmoother
EVSmooother = ExposureSmoother


class IntervalometerEngine:
    """Generates shot schedule and simulates capture with exposure smoothing."""

    def __init__(self, config: Any = None, **kwargs):
        if isinstance(config, IntervalometerConfig):
            self.config = config
        elif isinstance(config, dict):
            merged = dict(config)
            merged.update(kwargs)
            self.config = IntervalometerConfig(**merged) if merged else IntervalometerConfig()
        elif config is None:
            if kwargs:
                self.config = IntervalometerConfig(**kwargs)
            else:
                self.config = IntervalometerConfig()
        else:
            # maybe first positional is interval
            try:
                self.config = IntervalometerConfig(interval_sec=float(config), **kwargs)
            except Exception:
                self.config = IntervalometerConfig()

        cfg = self.config
        self.smoother = ExposureSmoother(
            window=cfg.smoothing_window,
            max_ev_step_per_frame=cfg.max_ev_step_per_frame,
        ) if cfg.exposure_smoothing else None

        # base exposure
        self.base_shutter = float(kwargs.get("base_shutter", kwargs.get("shutter", 1.0 / 60.0)))
        self.base_iso = int(kwargs.get("base_iso", kwargs.get("iso", 200)))
        self.base_aperture = float(kwargs.get("base_aperture", kwargs.get("aperture", 2.8)))
        self.current_ev = 0.0
        self._frames_done = 0

    # ---- schedule --------------------------------------------------------- #
    def generate_schedule(self) -> List[float]:
        return self.generate_shot_schedule()

    def generate_shot_schedule(self) -> List[float]:
        cfg = self.config
        if cfg.total_frames == 0:
            return []
        out = []
        t = cfg.start_delay_sec
        for i in range(cfg.total_frames):
            out.append(t + i * cfg.interval_sec)
        return out

    def shot_schedule(self) -> List[float]:
        return self.generate_shot_schedule()

    def schedule(self) -> List[float]:
        return self.generate_shot_schedule()

    def timestamps(self) -> List[float]:
        return self.generate_shot_schedule()

    def get_schedule(self) -> List[float]:
        return self.generate_shot_schedule()

    @property
    def frame_count(self) -> int:
        return self.config.total_frames

    # ---- capture simulation ----------------------------------------------- #
    def _exposure_for(self, scene_brightness: float) -> Dict[str, Any]:
        cfg = self.config
        delta = 0.0
        smoothed = None
        if cfg.exposure_smoothing and self.smoother is not None:
            res = self.smoother.update(scene_brightness)
            delta = res["delta_ev"]
            smoothed = res["smoothed"]
            self.current_ev += delta
        # apply ev to shutter: positive ev -> longer shutter (lower speed value)
        shutter = self.base_shutter * (2.0 ** self.current_ev)
        # iso adjustment if shutter hits bounds? keep simple
        iso = self.base_iso
        return {
            "shutter_speed": shutter,
            "iso": iso,
            "aperture": self.base_aperture,
            "ev_delta": delta,
            "ev_smoothed": smoothed if smoothed is not None else scene_brightness,
            "exposure_ev": self.current_ev,
        }

    def on_capture(self, frame_index: int = 0, scene_brightness: float = 0.0, **kwargs) -> Dict[str, Any]:
        sb = kwargs.get("luminance", kwargs.get("brightness", scene_brightness))
        if "scene" in kwargs:
            sb = kwargs["scene"]
        return self._exposure_for(float(sb))

    def on_frame_captured(self, *args, **kwargs):
        # flexible: first positional may be frame_index or brightness
        frame_index = kwargs.pop("frame_index", None)
        brightness = kwargs.pop("scene_brightness", kwargs.pop("brightness", kwargs.pop("luminance", None)))
        if frame_index is None and args:
            # if first arg is int and second present -> index
            if len(args) >= 2:
                frame_index = args[0]
                brightness = args[1] if brightness is None else brightness
            else:
                if brightness is None:
                    # guess
                    try:
                        brightness = float(args[0])
                        frame_index = 0
                    except (TypeError, ValueError):
                        frame_index = args[0]
                        brightness = 0.0
        if brightness is None:
            brightness = 0.0
        if frame_index is None:
            frame_index = 0
        return self.on_capture(frame_index=frame_index, scene_brightness=float(brightness), **kwargs)

    def capture(self, *args, **kwargs):
        return self.on_frame_captured(*args, **kwargs)

    def capture_frame(self, *args, **kwargs):
        return self.on_frame_captured(*args, **kwargs)

    def process_frame(self, *args, **kwargs):
        return self.on_frame_captured(*args, **kwargs)

    def simulate_frame(self, *args, **kwargs):
        return self.on_frame_captured(*args, **kwargs)

    def next_exposure(self, *args, **kwargs):
        return self.on_frame_captured(*args, **kwargs)

    def run(self, brightnesses: Sequence[float]) -> List[Dict[str, Any]]:
        out = []
        for i, b in enumerate(brightnesses):
            out.append(self.on_capture(frame_index=i, scene_brightness=float(b)))
        return out

    def simulate(self, brightnesses):
        return self.run(brightnesses)


# module-level helpers
def generate_schedule(config):
    eng = IntervalometerEngine(config)
    return eng.generate_schedule()


def ev_to_shutter(base_shutter, ev):
    return base_shutter * (2.0 ** ev)
