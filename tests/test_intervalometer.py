import math
import statistics
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.intervalometer import (
    IntervalometerConfig,
    ExposureSmoother,
    IntervalometerEngine,
)


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        c = IntervalometerConfig()
        self.assertEqual(c.interval_sec, 1.0)
        self.assertEqual(c.total_frames, 0)
        self.assertEqual(c.start_delay_sec, 0.0)
        self.assertFalse(c.exposure_smoothing)
        self.assertEqual(c.smoothing_window, 5)
        self.assertAlmostEqual(c.max_ev_step_per_frame, 0.1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            IntervalometerConfig(interval_sec=0)
        with self.assertRaises(ValueError):
            IntervalometerConfig(total_frames=-1)
        with self.assertRaises(ValueError):
            IntervalometerConfig(start_delay_sec=-1)
        with self.assertRaises(ValueError):
            IntervalometerConfig(smoothing_window=0)
        with self.assertRaises(ValueError):
            IntervalometerConfig(max_ev_step_per_frame=0)


class TestSchedule(unittest.TestCase):
    def test_basic(self):
        cfg = IntervalometerConfig(interval_sec=2.0, total_frames=5, start_delay_sec=1.0)
        eng = IntervalometerEngine(cfg)
        sched = eng.generate_schedule()
        self.assertEqual(len(sched), 5)
        self.assertAlmostEqual(sched[0], 1.0)
        self.assertAlmostEqual(sched[1], 3.0)
        self.assertAlmostEqual(sched[4], 9.0)

    def test_infinite_empty(self):
        cfg = IntervalometerConfig(interval_sec=1.0, total_frames=0)
        eng = IntervalometerEngine(cfg)
        self.assertEqual(eng.generate_schedule(), [])

    def test_aliases(self):
        cfg = IntervalometerConfig(interval_sec=1.0, total_frames=3, start_delay_sec=0.5)
        eng = IntervalometerEngine(cfg)
        self.assertEqual(eng.shot_schedule(), eng.generate_shot_schedule())
        self.assertEqual(eng.timestamps(), eng.schedule())


class TestSmoother(unittest.TestCase):
    def test_variance_reduction(self):
        raw = [10.0, 12.0, 9.0, 13.0, 8.0] * 4
        smoother = ExposureSmoother(window=5, max_ev_step_per_frame=0.5)
        smoothed = [smoother.update(v)["smoothed"] for v in raw]
        self.assertLess(statistics.pvariance(smoothed), statistics.pvariance(raw))

    def test_step_clamp(self):
        s = ExposureSmoother(window=3, max_ev_step_per_frame=0.1)
        r = s.update(5.0)
        self.assertLessEqual(abs(r["delta_ev"]), 0.1 + 1e-9)


class TestDayNightGradient(unittest.TestCase):
    def test_gradient_smooth(self):
        # day to night: brightness ramps down
        vals = [10.0 - 0.05 * i for i in range(60)]
        # add flicker
        import random
        random.seed(1)
        flicker = [v + (random.random() - 0.5) * 0.6 for v in vals]
        cfg = IntervalometerConfig(interval_sec=1.0, total_frames=60,
                                  exposure_smoothing=True, smoothing_window=5,
                                  max_ev_step_per_frame=0.1)
        eng = IntervalometerEngine(cfg)
        out = eng.run(flicker)
        evs = [o["ev_smoothed"] for o in out]
        # smoothed should track trend; variance of delta small
        deltas = [out[i]["ev_delta"] for i in range(1, len(out))]
        self.assertTrue(all(abs(d) <= 0.1 + 1e-9 for d in deltas))


class TestEngineCapture(unittest.TestCase):
    def test_returns_params(self):
        cfg = IntervalometerConfig(interval_sec=2.0, total_frames=3, exposure_smoothing=True)
        eng = IntervalometerEngine(cfg)
        r = eng.on_capture(0, 5.0)
        self.assertIn("shutter_speed", r)
        self.assertIn("iso", r)
        self.assertIn("aperture", r)


if __name__ == "__main__":
    unittest.main()
