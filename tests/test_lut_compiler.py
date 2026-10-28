import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.lut_compiler import (
    CubeLUTParser,
    DSPMatrixOptimizer,
    ToneCurveExtractor,
    PRESETS,
    PRESET_MATRICES,
    BUILTIN_PRESETS,
    get_preset,
    list_presets,
    MITIGATION_FIRMWARE,
)


CUBE_TEXT = """TITLE "test"
LUT_3D_SIZE 2
DOMAIN_MIN 0.0 0.0 0.0
DOMAIN_MAX 1.0 1.0 1.0
0.0 0.0 0.0
0.0 0.0 1.0
0.0 1.0 0.0
0.0 1.0 1.0
1.0 0.0 0.0
1.0 0.0 1.0
1.0 1.0 0.0
1.0 1.0 1.0
"""


class TestCubeParsing(unittest.TestCase):
    def test_parse_text(self):
        p = CubeLUTParser(CUBE_TEXT)
        self.assertEqual(p.title, "test")
        self.assertEqual(p.size, 2)
        self.assertEqual(len(p.entries), 8)
        self.assertEqual(len(p.data), 8)

    def test_parse_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".cube", delete=False) as f:
            f.write(CUBE_TEXT)
            path = f.name
        try:
            p = CubeLUTParser()
            p.parse_file(path)
            self.assertEqual(p.lut_size, 2)
        finally:
            Path(path).unlink(missing_ok=True)


class TestQ15(unittest.TestCase):
    def test_conversion_clamp(self):
        m = [1.0, 2.0, -2.0] + [0.0] * 6
        q = DSPMatrixOptimizer.to_q15(m)
        self.assertEqual(q[0], 32767)
        self.assertEqual(q[1], 32767)  # clamped from 65536
        self.assertEqual(q[2], -32768)  # clamped

    def test_fit_returns_q15(self):
        p = CubeLUTParser(CUBE_TEXT)
        opt = DSPMatrixOptimizer(p)
        mat = opt.fit(p)
        self.assertEqual(len(mat), 9)
        for v in mat:
            self.assertTrue(-32768 <= v <= 32767)
        self.assertEqual(opt.matrix, mat)
        self.assertEqual(opt.matrix_q15, mat)


class TestPresets(unittest.TestCase):
    def test_presets_exist(self):
        for name in ("Classic Negative", "Eterna Bleach Bypass", "Nostalgic Neg"):
            self.assertIn(name, PRESETS)
            self.assertIn(name, PRESET_MATRICES)
            self.assertIn(name, BUILTIN_PRESETS)
        self.assertEqual(len(list_presets()), 3)

    def test_preset_generation(self):
        for name in list_presets():
            p = get_preset(name)
            self.assertEqual(len(p["matrix"]), 9)
            for v in p["matrix"]:
                self.assertTrue(-32768 <= v <= 32767)


class TestToneCurve(unittest.TestCase):
    def test_extract(self):
        p = CubeLUTParser(CUBE_TEXT)
        tc = ToneCurveExtractor(p)
        curve = tc.extract(p)
        self.assertIsInstance(curve, list)
        self.assertEqual(len(curve), 2)
        self.assertEqual(tc.tone_curve, curve)


class TestCLI(unittest.TestCase):
    def test_help(self):
        res = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "lut_compiler.py"), "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery", res.stdout + res.stderr)

    def test_compile_cli(self):
        with tempfile.TemporaryDirectory() as d:
            cube = Path(d) / "t.cube"
            cube.write_text(CUBE_TEXT)
            out = Path(d) / "out.json"
            res = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "lut_compiler.py"), "compile", str(cube), "-o", str(out)],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(out.read_text())
            self.assertIn("matrix_q15", data)
            self.assertEqual(len(data["matrix_q15"]), 9)


if __name__ == "__main__":
    unittest.main()
