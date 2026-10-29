import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.clarity import ClarityFilter


def _sine_image(width=32, height=32):
    buf = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            v = 0.5 + 0.25 * math.sin(2 * math.pi * x / 6) + 0.15 * math.sin(2 * math.pi * y / 8)
            buf[y * width + x] = int(round(v * 255))
    return bytes(buf)


def _laplacian_variance(data, width, height):
    vals = []
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            c = data[y * width + x]
            lap = (
                data[(y - 1) * width + x]
                + data[(y + 1) * width + x]
                + data[y * width + (x - 1)]
                + data[y * width + (x + 1)]
                - 4 * c
            )
            vals.append(lap)
    mean = sum(vals) / len(vals)
    return sum((v - mean) ** 2 for v in vals) / len(vals)


class TestClarity(unittest.TestCase):
    def setUp(self):
        self.img = _sine_image()
        self.w = 32
        self.h = 32

    def test_neutral_identity(self):
        out = ClarityFilter().apply(self.img, self.w, self.h, 0)
        self.assertEqual(out, self.img)

    def test_positive_increases_contrast(self):
        base = ClarityFilter().apply(self.img, self.w, self.h, 0)
        pos = ClarityFilter().apply(self.img, self.w, self.h, 5)
        self.assertGreater(_laplacian_variance(pos, self.w, self.h),
                           _laplacian_variance(base, self.w, self.h))

    def test_negative_decreases_contrast(self):
        base = ClarityFilter().apply(self.img, self.w, self.h, 0)
        neg = ClarityFilter().apply(self.img, self.w, self.h, -5)
        self.assertLess(_laplacian_variance(neg, self.w, self.h),
                        _laplacian_variance(base, self.w, self.h))

    def test_bounds(self):
        cf = ClarityFilter()
        for lvl in range(-5, 6):
            out = cf.apply(self.img, self.w, self.h, lvl)
            self.assertEqual(len(out), len(self.img))
        for bad in (-6, 6, 10, -10):
            with self.assertRaises(ValueError):
                ClarityFilter().apply(self.img, self.w, self.h, bad)

    def test_normalized_float_input(self):
        f = [v / 255.0 for v in self.img]
        out = ClarityFilter().apply(f, self.w, self.h, 0)
        self.assertEqual(out, self.img)

    def test_constructor_level(self):
        out = ClarityFilter(clarity_level=0).apply(self.img, self.w, self.h)
        self.assertEqual(out, self.img)


if __name__ == "__main__":
    unittest.main()
