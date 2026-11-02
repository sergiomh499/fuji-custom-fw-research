"""Tests for the X-T5 firmware extractor."""

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.xt5_extractor import XT5Extractor, XT5_FILM_TOKENS

REAL = Path("/tmp/xt5_v431.bin")


class TestXT5Extractor(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(XT5Extractor))

    def test_tokens_present(self):
        for t in ("NOSTALGIC_NEG", "NEG_N", "NOSTALGIC", "BLEACH_BYPASS", "ETERNA_BB", "BYPASS", "REALA", "REALA_ACE"):
            self.assertIn(t, XT5_FILM_TOKENS)

    def test_synthetic_nostalgic_negative_matrix(self):
        marker = b"NOSTALGIC_NEG"
        vals = [4096, 100, -50, 0, 4096, 0, 0, 0, 4096]
        data = marker + b"\x00" * 4 + struct.pack("<9i", *vals) + b"\x00" * 8
        ext = XT5Extractor(data)
        res = ext.find_nostalgic_negative()
        self.assertGreaterEqual(len(res), 1)
        self.assertEqual(res[0]["matrix"], vals)

    def test_synthetic_bleach_bypass_matrix(self):
        marker = b"BLEACH_BYPASS"
        vals = [3800, 200, 96, 0, 3900, 0, 0, 0, 4000]
        data = marker + b"\x00" * 4 + struct.pack("<9i", *vals) + b"\x00" * 8
        ext = XT5Extractor(data)
        res = ext.find_bleach_bypass()
        self.assertGreaterEqual(len(res), 1)
        self.assertEqual(res[0]["matrix"], vals)

    def test_synthetic_reala_matrix(self):
        marker = b"REALA_ACE"
        vals = [4096] * 9
        data = marker + b"\x00" * 4 + struct.pack("<9i", *vals) + b"\x00" * 8
        ext = XT5Extractor(data)
        res = ext.find_reala()
        self.assertGreaterEqual(len(res), 1)
        self.assertEqual(res[0]["matrix"], vals)

    def test_synthetic_neg_n_and_nostalgic(self):
        data = b"NEG_N" + struct.pack("<9i", *([4096]*9)) + b"NOSTALGIC" + struct.pack("<9i", *([4096]*9))
        ext = XT5Extractor(data, search_range=(0, len(data)))
        toks = {d["token"] for d in ext.extract_descriptors()}
        self.assertTrue({"NEG_N", "NOSTALGIC"} <= toks)

    def test_synthetic_variants(self):
        data = (b"ETERNA_BB" + struct.pack("<9i", *([4096]*9)) +
                b"BYPASS" + struct.pack("<9i", *([4096]*9)) +
                b"REALA" + struct.pack("<9i", *([4096]*9)))
        ext = XT5Extractor(data, search_range=(0, len(data)))
        toks = {d["token"] for d in ext.extract_descriptors()}
        self.assertTrue({"ETERNA_BB", "REALA"} <= toks)

    def test_q15_scale(self):
        matrix = [32768, 8192, -4096, 0, 32768, 0, 0, 0, 32768]
        data = b"MONO" + struct.pack("<9i", *matrix)
        ext = XT5Extractor(data, search_range=(0, len(data)))
        descs = ext.extract_descriptors(scale=32768)
        self.assertEqual(descs[0]["scale"], 32768)

    def test_tone_curves(self):
        matrix = [4096] * 9
        lut = [1, 2, 3, 4]
        data = b"ACROS" + struct.pack("<9i", *matrix) + struct.pack("<4i", *lut)
        ext = XT5Extractor(data, search_range=(0, len(data)))
        tc = ext.extract_tone_curves(count=4)
        self.assertEqual(len(tc), 1)
        self.assertEqual(tc[0]["values"], lut)

    def test_extract_matrices(self):
        marker = b"CLASSIC_NEG"
        vals = [4096] * 9
        data = marker + b"\x00" * 4 + struct.pack("<9i", *vals) + b"\x00" * 8
        ext = XT5Extractor(data)
        mats = ext.extract_matrices()
        self.assertIn("CLASSIC_NEG", mats)
        self.assertEqual(mats["CLASSIC_NEG"], vals)

    def test_analyze_returns_dict(self):
        data = b"\x00" * 128
        ext = XT5Extractor(data)
        res = ext.analyze()
        self.assertIn("nostalgic_negative", res)
        self.assertIn("bleach_bypass", res)
        self.assertIn("reala", res)
        self.assertIn("matrices", res)
        self.assertIn("tone_curves", res)
        self.assertIn("sensor_resolution", res)
        self.assertIn("architecture_header", res)
        self.assertIn("mitigations", res)

    def test_sensor_resolution(self):
        data = b"xxxx40.2MP" + b"\x00" * 4
        ext = XT5Extractor(data)
        res = ext.find_sensor_resolution()
        self.assertGreater(len(res), 0)

    def test_architecture_header(self):
        data = b"yyyyX-Processor 5" + b"\x00" * 4
        ext = XT5Extractor(data)
        res = ext.find_architecture_header()
        self.assertGreater(len(res), 0)

    def test_path_constructor(self):
        import tempfile, os
        fd, p = tempfile.mkstemp()
        os.close(fd)
        Path(p).write_bytes(b"REALA" + struct.pack("<9i", *([4096]*9)))
        ext = XT5Extractor(path=p)
        self.assertGreater(len(ext.data), 0)
        Path(p).unlink()

    def test_module_level_helpers(self):
        from core import xt5_extractor
        data = b"NOSTALGIC" + struct.pack("<9i", *([4096]*9))
        self.assertTrue(isinstance(xt5_extractor.analyze_xt5(data), dict))


if __name__ == "__main__":
    unittest.main()
