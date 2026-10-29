"""Tests for the X-T20 firmware extractor."""

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.xt20_extractor import XT20Extractor

BIN = Path("/tmp/xt20_v211.bin")


class TestXT20Extractor(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(XT20Extractor))

    def test_header_parsing_unpacked_binary(self):
        if not BIN.exists():
            self.skipTest("binary not available")
        data = BIN.read_bytes()
        ext = XT20Extractor(data)
        h = ext.parse_header()
        self.assertTrue(h is None or isinstance(h, dict))

    def test_vector_scan(self):
        data = struct.pack("<8I", *range(8)) + b"\x00" * 64
        ext = XT20Extractor(data)
        vecs = ext.scan_vectors()
        self.assertEqual(len(vecs), 8)
        self.assertEqual(vecs[0], 0)

    def test_synthetic_acros_descriptor(self):
        matrix = [4096, 100, -50, 0, 4096, 0, 0, 0, 4096]
        lut = [0, 1024, 2048, 4095]
        data = b"ACROS" + struct.pack("<9i", *matrix) + struct.pack("<4i", *lut) + b"\x00" * 8
        ext = XT20Extractor(data, search_range=(0, len(data)))
        descs = ext.extract_acros_descriptors()
        self.assertEqual(len(descs), 1)
        self.assertEqual(descs[0]["token"], "ACROS")
        self.assertEqual(descs[0]["matrix"], matrix)
        self.assertEqual(descs[0]["matrix_offset"], 5)
        self.assertEqual(descs[0]["tone_lut_offset"], 5 + 36)

    def test_synthetic_variants(self):
        data = b"ACROS_YE" + struct.pack("<9i", *([4096]*9)) + b"ACROS_R" + struct.pack("<9i", *([4096]*9)) + b"ACROS_G" + struct.pack("<9i", *([4096]*9))
        ext = XT20Extractor(data, search_range=(0, len(data)))
        toks = {d["token"] for d in ext.extract_acros_descriptors()}
        self.assertTrue({"ACROS_YE", "ACROS_R", "ACROS_G"} <= toks)

    def test_q15_scale(self):
        matrix = [32768, 8192, -4096, 0, 32768, 0, 0, 0, 32768]
        data = b"MONO" + struct.pack("<9i", *matrix)
        ext = XT20Extractor(data, search_range=(0, len(data)))
        descs = ext.extract_acros_descriptors(scale=32768)
        self.assertEqual(descs[0]["scale"], 32768)
        self.assertEqual(descs[0]["matrix"], matrix)

    def test_bw_token(self):
        matrix = [4096] * 9
        data = b"BW_" + struct.pack("<9i", *matrix)
        ext = XT20Extractor(data, search_range=(0, len(data)))
        descs = ext.extract_acros_descriptors()
        self.assertEqual(descs[0]["token"], "BW_")

    def test_tone_curves(self):
        matrix = [4096] * 9
        lut = [1, 2, 3, 4]
        data = b"ACROS" + struct.pack("<9i", *matrix) + struct.pack("<4i", *lut)
        ext = XT20Extractor(data, search_range=(0, len(data)))
        tc = ext.extract_tone_curves(count=4)
        self.assertEqual(len(tc), 1)
        self.assertEqual(tc[0]["values"], lut)

    def test_analyze_returns_dict(self):
        data = b"\x00" * 128
        ext = XT20Extractor(data)
        res = ext.analyze()
        self.assertIn("acros", res)
        self.assertIn("wifi", res)
        self.assertIn("mitigations", res)

    def test_wifi_analysis_real(self):
        if not BIN.exists():
            self.skipTest("binary not available")
        data = BIN.read_bytes()
        ext = XT20Extractor(data)
        wifi = ext.analyze_wifi()
        self.assertIn("recv_memory_depletion", wifi["markers"])
        self.assertTrue(wifi["markers"]["recv_memory_depletion"])

    def test_wifi_comparison(self):
        data = b"\x00" * 128
        ext = XT20Extractor(data)
        comp = ext.compare_wifi_with_xt10()
        self.assertIn("xt10_vulnerable_sites", comp)
        self.assertEqual(comp["xt10_vulnerable_sites"]["recv_memory_depletion"], 0x00B4DD9C)


if __name__ == "__main__":
    unittest.main()
