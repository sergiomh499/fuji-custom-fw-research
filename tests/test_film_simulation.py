import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.film_simulation import FilmSimulationExtractor, FilmSimulationPatcher

BIN = Path("/tmp/xt10_v131.bin")


class TestFilmSimulation(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(FilmSimulationExtractor))
        self.assertTrue(callable(FilmSimulationPatcher))

    def test_parse_tokens_actual(self):
        if not BIN.exists():
            self.skipTest("binary not available")
        data = BIN.read_bytes()
        ext = FilmSimulationExtractor(data)
        toks = ext.parse_tokens()
        self.assertIsInstance(toks, list)
        self.assertGreater(len(toks), 0)
        names = {t["token"] for t in toks}
        self.assertTrue(names & {"PROV", "CHROME", "SEP", "ASTIA", "_ASTIA"})

    def test_descriptor_offsets_in_range(self):
        if not BIN.exists():
            self.skipTest("binary not available")
        data = BIN.read_bytes()
        ext = FilmSimulationExtractor(data)
        descs = ext.extract_descriptors()
        for d in descs:
            self.assertGreaterEqual(d["offset"], 0x0024FB10)
            self.assertLess(d["offset"], 0x0024FB70)

    def test_synthetic_roundtrip(self):
        # Build a synthetic block: token + 9 Q12 ints + 4 LUT ints
        matrix = [4096, 100, -50, 0, 4096, 0, 0, 0, 4096]
        lut = [0, 1024, 2048, 4095]
        data = b"PROV" + struct.pack("<9i", *matrix) + struct.pack("<4i", *lut) + b"\x00" * 8
        ext = FilmSimulationExtractor(data, search_range=(0, len(data)))
        descs = ext.extract_descriptors()
        self.assertEqual(len(descs), 1)
        self.assertEqual(descs[0]["token"], "PROV")
        self.assertEqual(descs[0]["matrix"], matrix)
        self.assertEqual(descs[0]["matrix_offset"], 4)

        new_matrix = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        patcher = FilmSimulationPatcher(data)
        patcher.set_matrix("PROV", new_matrix)
        patched = patcher.generate()
        ext2 = FilmSimulationExtractor(patched, search_range=(0, len(patched)))
        self.assertEqual(ext2.extract_matrices()["PROV"], new_matrix)

    def test_float_dtype(self):
        matrix = [1.0, 0.25, -0.1, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        data = b"VEL" + struct.pack("<9f", *matrix)
        ext = FilmSimulationExtractor(data, search_range=(0, len(data)))
        descs = ext.extract_descriptors(dtype="f")
        self.assertEqual(len(descs), 1)
        for a, b in zip(descs[0]["matrix"], matrix):
            self.assertAlmostEqual(a, b, places=5)

    def test_swap_roundtrip(self):
        m1 = list(range(1, 10))
        m2 = list(range(10, 19))
        data = b"PROV" + struct.pack("<9i", *m1) + b"CHROME" + struct.pack("<9i", *m2)
        patcher = FilmSimulationPatcher(data)
        patcher.swap_matrices("PROV", "CHROME")
        out = patcher.generate()
        ext = FilmSimulationExtractor(out, search_range=(0, len(out)))
        mats = ext.extract_matrices()
        self.assertEqual(mats["PROV"], m2)
        self.assertEqual(mats["CHROME"], m1)

    def test_inject_lut(self):
        matrix = [4096] * 9
        data = b"SEP" + struct.pack("<9i", *matrix)
        patcher = FilmSimulationPatcher(data)
        lut = [10, 20, 30]
        patcher.inject_lut("SEP", lut)
        out = patcher.to_bytes()
        ext = FilmSimulationExtractor(out, search_range=(0, len(out)))
        d = ext.extract_descriptors()[0]
        self.assertEqual(d["tone_lut_offset"], 3 + 36)
        # read lut back
        vals = struct.unpack("<3i", out[d["tone_lut_offset"]:d["tone_lut_offset"] + 12])
        self.assertEqual(list(vals), lut)


if __name__ == "__main__":
    unittest.main()
