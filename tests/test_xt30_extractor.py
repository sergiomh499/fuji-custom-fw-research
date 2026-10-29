"""Tests for the X-T30 firmware extractor."""

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.xt30_extractor import XT30Extractor

REAL = Path("/tmp/xt30_v201.bin")


class TestXT30Extractor(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(XT30Extractor))

    def test_synthetic_classic_negative_matrix(self):
        marker = b"NEG_C"
        vals = [4096, 100, -50, 0, 4096, 0, 0, 0, 4096]
        data = marker + b"\x00" * 4 + struct.pack("<9i", *vals) + b"\x00" * 8
        ext = XT30Extractor(data)
        res = ext.find_classic_negative()
        self.assertGreaterEqual(len(res), 1)
        self.assertEqual(res[0]["matrix"], vals)

    def test_synthetic_eterna_matrix(self):
        marker = b"ETERNA"
        vals = [3800, 200, 96, 0, 3900, 0, 0, 0, 4000]
        data = marker + b"\x00" * 4 + struct.pack("<9i", *vals) + b"\x00" * 8
        ext = XT30Extractor(data)
        res = ext.find_eterna()
        self.assertGreaterEqual(len(res), 1)
        self.assertEqual(res[0]["matrix"], vals)

    def test_synthetic_color_chrome_marker(self):
        data = b"xxxxCOLOR_CHROME" + struct.pack("<4f", 0.25, 0.12, 0.28, 180.0) + b"\x00" * 8
        ext = XT30Extractor(data)
        res = ext.find_color_chrome()
        self.assertGreaterEqual(len(res), 1)
        self.assertEqual(res[0]["marker"], "COLOR_CHROME")

    def test_extract_matrices_synthetic(self):
        marker = b"CLASSIC_NEG"
        vals = [4096] * 9
        data = marker + b"\x00" * 4 + struct.pack("<9i", *vals) + b"\x00" * 8
        ext = XT30Extractor(data)
        mats = ext.extract_matrices()
        self.assertIn("CLASSIC_NEG", mats)
        self.assertEqual(mats["CLASSIC_NEG"], vals)

    def test_analyze_real_binary(self):
        if not REAL.exists():
            self.skipTest("real binary missing")
        ext = XT30Extractor(REAL)
        res = ext.analyze()
        self.assertIn("classic_negative", res)
        self.assertIn("eterna", res)
        self.assertIn("color_chrome", res)
        self.assertIn("matrices", res)

    def test_real_binary_color_chrome_markers(self):
        if not REAL.exists():
            self.skipTest("real binary missing")
        ext = XT30Extractor(REAL)
        res = ext.find_color_chrome()
        self.assertGreater(len(res), 0)

    def test_thresholds(self):
        ext = XT30Extractor(b"")
        t = ext.color_chrome_thresholds
        self.assertEqual(t["saturation_threshold"], 0.25)

    def test_path_constructor(self):
        if not REAL.exists():
            self.skipTest("real binary missing")
        ext = XT30Extractor(path=str(REAL))
        self.assertGreater(len(ext.data), 0)


if __name__ == "__main__":
    unittest.main()
