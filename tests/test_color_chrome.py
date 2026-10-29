import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.color_chrome import (
    ColorChromeLevel,
    ColorChromeConfig,
    ColorChromeProcessor,
)


class TestColorChrome(unittest.TestCase):
    def test_neutral_off_identity_pixel(self):
        proc = ColorChromeProcessor(ColorChromeLevel.OFF, ColorChromeLevel.OFF)
        for rgb in ((0, 0, 0), (128, 128, 128), (255, 255, 255), (10, 20, 30)):
            self.assertEqual(proc.process_pixel(*rgb), rgb)

    def test_neutral_off_identity_image(self):
        buf = bytes([10, 20, 30, 40, 50, 60, 200, 100, 50])
        proc = ColorChromeProcessor(chrome_level=ColorChromeLevel.OFF, chrome_blue_level=ColorChromeLevel.OFF)
        self.assertEqual(proc.process_image(buf, 1, 3), buf)

    def test_red_warm_compression_strong(self):
        proc = ColorChromeProcessor(chrome_level=ColorChromeLevel.STRONG, chrome_blue_level=ColorChromeLevel.OFF)
        r, g, b = proc.process_pixel(255, 0, 0)
        self.assertLess(r, 255)
        # blue channel untouched
        self.assertEqual((g, b), (0, 0))

    def test_red_weak_less_than_strong(self):
        weak = ColorChromeProcessor(chrome_level=ColorChromeLevel.WEAK).process_pixel(255, 0, 0)[0]
        strong = ColorChromeProcessor(chrome_level=ColorChromeLevel.STRONG).process_pixel(255, 0, 0)[0]
        self.assertGreaterEqual(weak, strong)

    def test_blue_darkening_active_vs_inactive(self):
        inactive = ColorChromeProcessor(chrome_blue_level=ColorChromeLevel.OFF)
        active = ColorChromeProcessor(chrome_blue_level=ColorChromeLevel.STRONG)
        px = (0, 100, 255)
        r0, g0, b0 = inactive.process_pixel(*px)
        r1, g1, b1 = active.process_pixel(*px)
        # active should darken (blue lower)
        self.assertLessEqual(b1, b0)
        # and differ
        self.assertNotEqual((r1, g1, b1), (r0, g0, b0))

    def test_gray_white_unaffected(self):
        for lvl in (ColorChromeLevel.OFF, ColorChromeLevel.WEAK, ColorChromeLevel.STRONG):
            for blvl in (ColorChromeLevel.OFF, ColorChromeLevel.WEAK, ColorChromeLevel.STRONG):
                proc = ColorChromeProcessor(chrome_level=lvl, chrome_blue_level=blvl)
                for v in (0, 128, 255):
                    self.assertEqual(proc.process_pixel(v, v, v), (v, v, v))

    def test_config_dataclass(self):
        cfg = ColorChromeConfig(chrome_level="STRONG", chrome_blue_level="WEAK")
        self.assertEqual(cfg.chrome_level, ColorChromeLevel.STRONG)
        self.assertEqual(cfg.chrome_blue_level, ColorChromeLevel.WEAK)

    def test_process_image_length(self):
        buf = bytes([255, 0, 0, 0, 0, 255] * 2)
        proc = ColorChromeProcessor(chrome_level=ColorChromeLevel.STRONG, chrome_blue_level=ColorChromeLevel.STRONG)
        out = proc.process_image(buf, 2, 2)
        self.assertEqual(len(out), len(buf))


if __name__ == "__main__":
    unittest.main()
