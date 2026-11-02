import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline_runner import PipelineRunner
from core.recipe import Recipe, BUILTIN_RECIPES


def make_gradient(w=8, h=8):
    buf = bytearray()
    for y in range(h):
        for x in range(w):
            buf.extend((x * 32 % 256, y * 32 % 256, (x + y) * 16 % 256))
    return bytes(buf)


class TestPipelineRunner(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(PipelineRunner))

    def test_identity_provia_runs(self):
        data = make_gradient()
        r = PipelineRunner(data, width=8, height=8, simulation="Provia")
        out = r.run()
        self.assertEqual(len(out), len(data))
        self.assertEqual(out, data)

    def test_stage_inactive_identity(self):
        data = make_gradient()
        r = PipelineRunner(data, width=8, height=8, simulation="Provia", grain="OFF", clarity=0)
        self.assertEqual(r.run(), data)

    def test_recipe_application(self):
        data = make_gradient()
        rec = BUILTIN_RECIPES["C1"]
        r = PipelineRunner(data, width=8, height=8, recipe=rec)
        out = r.run()
        self.assertEqual(len(out), len(data))
        self.assertNotEqual(out, data)

    def test_individual_stages(self):
        data = make_gradient()
        r = PipelineRunner(data, width=8, height=8, simulation="Classic Negative", grain="STRONG", clarity=2,
                           chrome_level="STRONG", wb_shift_r=2, wb_shift_b=-1, highlight=1, shadow=1, seed=1)
        # white balance
        wb = r.apply_white_balance(data)
        self.assertNotEqual(wb, data)
        # color matrix
        cm = r.apply_color_matrix(data)
        self.assertNotEqual(cm, data)
        # color chrome
        cc = r.apply_color_chrome(data)
        # may or may not differ; length ok
        self.assertEqual(len(cc), len(data))
        # clarity
        cl = r.apply_clarity(data)
        self.assertEqual(len(cl), len(data))
        # tone
        tc = r.apply_tone_curve(data)
        self.assertEqual(len(tc), len(data))
        # grain
        gr = r.apply_grain(data)
        self.assertEqual(len(gr), len(data))

    def test_ppm_roundtrip(self):
        import tempfile, os
        data = make_gradient(4, 4)
        d = tempfile.mkdtemp()
        inp = os.path.join(d, "in.ppm")
        outp = os.path.join(d, "out.ppm")
        PipelineRunner.write_ppm(inp, 4, 4, data)
        w, h, rd = PipelineRunner.read_ppm(inp)
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(rd, data)
        r = PipelineRunner.from_ppm(inp, simulation="Acros", grain="WEAK", seed=2)
        r.to_ppm(outp)
        w2, h2, rd2 = PipelineRunner.read_ppm(outp)
        self.assertEqual((w2, h2), (4, 4))
        self.assertEqual(len(rd2), len(data))

    def test_raw_serialization(self):
        data = make_gradient(4, 4)
        r = PipelineRunner(data, width=4, height=4, simulation="Reala ACE")
        raw = r.to_raw()
        self.assertIsInstance(raw, (bytes, bytearray))
        self.assertEqual(len(raw), len(data))

    def test_grain_off_identity(self):
        data = make_gradient()
        r = PipelineRunner(data, width=8, height=8, simulation="Provia", grain="OFF")
        self.assertEqual(r.run(), data)

    def test_color_checker_patches(self):
        # 2x2 patches
        data = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255])
        r = PipelineRunner(data, width=2, height=2, simulation="Sepia")
        out = r.run()
        self.assertEqual(len(out), len(data))


if __name__ == "__main__":
    unittest.main()
