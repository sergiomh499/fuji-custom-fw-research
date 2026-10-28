"""Tests for the FinePix X10 firmware analyzer."""

import struct
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUJITOOL = ROOT / "fujitool"

sys.path.insert(0, str(ROOT))

from core.x10_analyzer import X10Analyzer


def _make_type4_header(model_code="0001022", v1=2, v2=1):
    code_size = 512
    code_bytes = bytearray(code_size)
    for i, c in enumerate(model_code):
        idx = 1 + i * 2
        if idx < code_size:
            code_bytes[idx] = ord(c)
            code_bytes[idx - 1] = ord("3")
    header = struct.pack("<I", 4) + bytes(code_bytes) + struct.pack("<IIII", v1, v2, 0x38261731, 0)
    return header


class TestX10Analyzer(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(X10Analyzer))

    def test_header_parsing_synthetic(self):
        header = _make_type4_header()
        data = header + b"\x00" * 64
        analyzer = X10Analyzer(data)
        h = analyzer.parse_header()
        self.assertIsNotNone(h)
        self.assertEqual(h["os_type"], 4)
        self.assertEqual(h["v1"], 2)
        self.assertEqual(h["v2"], 1)
        self.assertIn("0001022", h["model_code"])

    def test_header_parsing_unpacked_binary(self):
        # No Type-4 header -> None-ish but analyzer still works.
        data = b"\x00" * 128
        analyzer = X10Analyzer(data)
        # parse_header may return None for non-container; ensure no crash
        self.assertTrue(hasattr(analyzer, "header"))

    def test_vector_scan_length(self):
        data = struct.pack("<8I", *range(8)) + b"\x00" * 64
        analyzer = X10Analyzer(data)
        vecs = analyzer.scan_vectors()
        self.assertEqual(len(vecs), 8)
        self.assertEqual(vecs[0], 0)

    def test_vector_table_detection(self):
        # Build a synthetic vector table of branch instructions.
        words = [0xEA000010 + i for i in range(8)]
        data = struct.pack("<8I", *words) + b"\x00" * 64
        analyzer = X10Analyzer(data)
        tables = analyzer.find_vector_tables()
        self.assertGreaterEqual(len(tables), 1)
        self.assertEqual(tables[0]["offset"], 0)

    def test_printim_scan_synthetic(self):
        data = b"xxxxPRINTIM" + struct.pack("<I", 0x00516C90) + b"\x00" * 16
        analyzer = X10Analyzer(data)
        res = analyzer.find_printim()
        self.assertEqual(res["string_offset"], 4)
        self.assertEqual(res["entry_point"], 0x00516C90)
        self.assertGreaterEqual(len(res["entry_refs"]), 1)

    def test_lens_barrel_scan_synthetic(self):
        data = b"foo BARREL rotary SWITCH poweron" + b"\x00" * 8
        analyzer = X10Analyzer(data)
        res = analyzer.find_lens_barrel()
        self.assertGreater(len(res["marker_offsets"]), 0)

    def test_color_matrix_scan_synthetic(self):
        marker = b"COLOR_MATRIX"
        vals = [4096, 100, -50, 0, 4096, 0, 0, 0, 4096]
        # store as unsigned for struct; use large values? Use int32.
        import struct as _s
        data = marker + b"\x00" * 4 + _s.pack("<9i", *vals) + b"\x00" * 8
        analyzer = X10Analyzer(data)
        res = analyzer.find_color_matrices()
        self.assertGreaterEqual(len(res), 1)
        self.assertEqual(res[0]["values"], vals)

    def test_analyze_returns_dict(self):
        data = _make_type4_header() + b"\x00" * 64
        analyzer = X10Analyzer(data)
        res = analyzer.analyze()
        self.assertIn("header", res)
        self.assertIn("vectors", res)
        self.assertIn("printim", res)
        self.assertIn("lens_barrel", res)
        self.assertIn("color_matrices", res)
        self.assertIn("mitigations", res)

    def test_cli_help_mentions_mitigation(self):
        res = subprocess.run(
            [sys.executable, str(FUJITOOL), "analyze", "x10", "--help"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        out = res.stdout + res.stderr
        self.assertIn("BRICK_ANALYSIS_AND_RECOVERY.md", out)

    def test_cli_execution_missing_file(self):
        res = subprocess.run(
            [sys.executable, str(FUJITOOL), "analyze", "x10", "nonexistent.bin"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(res.returncode, 0)

    def test_cli_execution_synthetic(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "synth.bin"
            p.write_bytes(_make_type4_header() + b"PRINTIM" + b"\x00" * 64)
            res = subprocess.run(
                [sys.executable, str(FUJITOOL), "analyze", "x10", str(p)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("X10 Firmware Analysis", res.stdout)


if __name__ == "__main__":
    unittest.main()
