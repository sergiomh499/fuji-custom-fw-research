import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.auto_iso import (
    AutoISOSlot, AutoISOManager, quantize_shutter, shutter_string,
    CROP_XT10, CROP_X10, STANDARD_SHUTTERS, SHIFT_MULTIPLIERS,
)


class TestAutoIsoImport(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(AutoISOSlot))
        self.assertTrue(callable(AutoISOManager))


class TestSlotCreation(unittest.TestCase):
    def test_create_slot(self):
        s = AutoISOSlot("AUTO1", 200, 3200, "AUTO", None, "Standard")
        self.assertEqual(s.slot_id, "AUTO1")
        self.assertEqual(s.default_iso, 200)
        self.assertEqual(s.max_iso, 3200)
        self.assertTrue(s.is_auto)

    def test_fixed_mode(self):
        s = AutoISOSlot("AUTO2", 200, 6400, "1/60")
        self.assertEqual(s.min_shutter_mode, "fixed")
        self.assertAlmostEqual(s.min_shutter_seconds, 1/60, places=5)

    def test_iso_validation(self):
        with self.assertRaises(ValueError):
            AutoISOSlot("AUTO1", 100, 3200)
        with self.assertRaises(ValueError):
            AutoISOSlot("AUTO1", 200, 20000)
        with self.assertRaises(ValueError):
            AutoISOSlot("AUTO1", 800, 400)  # default > max

    def test_manager_defaults(self):
        m = AutoISOManager()
        self.assertIn("AUTO1", m.slots)
        self.assertIn("AUTO2", m.slots)
        self.assertIn("AUTO3", m.slots)
        self.assertEqual(m.active_slot_id, "AUTO1")

    def test_select_slot(self):
        m = AutoISOManager()
        m.select_slot("AUTO2")
        self.assertEqual(m.active_slot_id, "AUTO2")
        with self.assertRaises(ValueError):
            m.select_slot("AUTO9")


class TestQuantizer(unittest.TestCase):
    def test_quantize_exact(self):
        self.assertAlmostEqual(quantize_shutter(1/60), 1/60, places=6)

    def test_quantize_nearest(self):
        # 1/75 -> nearest 1/80 or 1/60; expect 1/80 (closer)
        self.assertAlmostEqual(quantize_shutter(1/75), 1/80, places=6)


class TestFocalShutter(unittest.TestCase):
    def test_prime_35mm(self):
        m = AutoISOManager()
        sec = m.calculate_min_shutter(35, CROP_XT10)
        # eq = 52.5, 1/52.5 = 0.0190 -> nearest 1/50
        self.assertAlmostEqual(sec, 1/50, places=6)

    def test_prime_56mm(self):
        m = AutoISOManager()
        sec = m.calculate_min_shutter(56, CROP_XT10)
        # eq=84, 1/84=0.0119 -> nearest 1/80
        self.assertAlmostEqual(sec, 1/80, places=6)

    def test_zoom_18_vs_55(self):
        m = AutoISOManager()
        s18 = m.calculate_min_shutter(18, CROP_XT10)
        s55 = m.calculate_min_shutter(55, CROP_XT10)
        self.assertGreater(1/s55, 1/s18)  # 55mm -> faster shutter

    def test_x10_crop(self):
        m = AutoISOManager()
        sec = m.calculate_min_shutter(18, CROP_X10)
        # eq=70.74, 1/70.74=0.0141 -> nearest 1/60? or 1/80? 0.0141 closer to 1/60? 0.0167 diff .0026 vs .0125 diff .0016 -> 1/80
        self.assertAlmostEqual(sec, 1/80, places=6)


class TestShiftModes(unittest.TestCase):
    def _calc(self, shift):
        m = AutoISOManager()
        slot = AutoISOSlot("AUTO1", 200, 3200, "AUTO", None, shift)
        m.add_slot(slot); m.select_slot("AUTO1")
        return m.calculate_min_shutter(35, CROP_XT10, shift_rate=shift)

    def test_faster(self):
        sec = self._calc("Faster")
        # mult=4, eq=52.5, 1/210=0.00476 -> nearest 1/200? or 1/250? 0.005 vs 0.004 diff .00024/.00076 -> 1/200
        self.assertAlmostEqual(sec, 1/200, places=6)

    def test_fast(self):
        sec = self._calc("Fast")
        # mult=2, 1/105=0.00952 -> nearest 1/100
        self.assertAlmostEqual(sec, 1/100, places=6)

    def test_standard(self):
        sec = self._calc("Standard")
        self.assertAlmostEqual(sec, 1/50, places=6)

    def test_slow(self):
        sec = self._calc("Slow")
        # mult=0.5, 1/26.25=0.0381 -> nearest 1/30? or 1/40? 0.0333 diff .0048 vs .025 diff .0131 -> 1/30
        self.assertAlmostEqual(sec, 1/30, places=6)

    def test_slower(self):
        sec = self._calc("Slower")
        # mult=0.25, 1/13.125=0.07619 -> nearest 1/125? wait 0.008? no 0.076 sec = 1/13.1, nearest 1/15? not in list; 1/10=0.1 or 1/15? standard has 1/8? Actually list min 1/30=0.0333. 0.076 is slower than 1/30, clamp to 1/30 (min). 
        self.assertAlmostEqual(sec, 1/30, places=6)


if __name__ == "__main__":
    unittest.main()
