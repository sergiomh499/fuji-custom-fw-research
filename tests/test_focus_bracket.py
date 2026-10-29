import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.focus_bracket import (
    FocusBracketConfig,
    FocusBracketPlanner,
    circle_of_confusion,
    hyperfocal_distance,
    dof_limits,
    depth_of_field,
    distance_to_steps,
    CMD_LENS_MOVE_STEP,
    LENS_GET_POSITION,
    LENS_SET_POSITION,
    INFINITY_SENTINEL,
    COC_APS_C,
    COC_X10,
)


class TestFocusBracket(unittest.TestCase):
    def test_dof_35mm_f14(self):
        h = hyperfocal_distance(35, 1.4)
        self.assertGreater(h, 0)
        n, f = dof_limits(35, 1.4, 2.0)
        self.assertGreater(f, n)
        self.assertAlmostEqual(circle_of_confusion("aps-c"), 0.020)

    def test_dof_56mm_f12(self):
        h = hyperfocal_distance(56, 1.2)
        self.assertGreater(h, 0)
        n, f = dof_limits(56, 1.2, 2.0)
        self.assertGreater(f, n)

    def test_dof_1855_at_55(self):
        h = hyperfocal_distance(55, 4.0)
        self.assertGreater(h, 0)
        n, f = dof_limits(55, 4.0, 2.0)
        self.assertGreater(f, n)
        self.assertAlmostEqual(depth_of_field(55, 4.0, 2.0), (2*4*(0.020/1000)*4)/(0.055**2), places=3)

    def test_constants(self):
        self.assertEqual(CMD_LENS_MOVE_STEP, 0x12)
        self.assertEqual(LENS_GET_POSITION, 0x21)
        self.assertEqual(LENS_SET_POSITION, 0x23)

    def test_config_validation(self):
        with self.assertRaises(ValueError):
            FocusBracketConfig(frames=0)
        with self.assertRaises(ValueError):
            FocusBracketConfig(step_scale=0)
        with self.assertRaises(ValueError):
            FocusBracketConfig(step_scale=11)

    def test_sequence_monotonic_and_clamp(self):
        cfg = FocusBracketConfig(frames=5, step_scale=3, interval_sec=0.5, far_limit_m=float('inf'))
        planner = FocusBracketPlanner(cfg, focal_length_mm=35, aperture=1.4)
        seq = planner.generate_sequence()
        self.assertEqual(len(seq), 5)
        # monotonic non-increasing finite prefix
        finite = [p for p in seq if p != INFINITY_SENTINEL]
        self.assertTrue(all(finite[i] >= finite[i+1] for i in range(len(finite)-1)))
        # last clamped to infinity
        self.assertEqual(seq[-1], INFINITY_SENTINEL)

    def test_frame_count_and_overlap(self):
        cfg = FocusBracketConfig(frames=10, step_scale=2, interval_sec=1.0, overlap_percent=0.25)
        planner = FocusBracketPlanner(cfg, focal_length_mm=56, aperture=1.2)
        seq = planner.generate_sequence()
        self.assertEqual(len(seq), 10)
        cmds = planner.generate_commands()
        self.assertEqual(len(cmds), 9)
        for c, d in cmds:
            self.assertEqual(c, 0x12)
        self.assertAlmostEqual(planner.overlap(), 0.25)

    def test_distance_to_steps(self):
        self.assertEqual(distance_to_steps(0), INFINITY_SENTINEL)
        self.assertEqual(distance_to_steps(1.5), 667)
        self.assertEqual(distance_to_steps(float("inf")), INFINITY_SENTINEL)


if __name__ == "__main__":
    unittest.main()
