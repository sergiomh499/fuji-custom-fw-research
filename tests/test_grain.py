import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.grain import (
    GrainRoughness,
    GrainSize,
    GrainConfig,
    GrainSynthesizer,
    density_weight,
)


class TestGrain(unittest.TestCase):
    def test_density_curve_modulation(self):
        self.assertAlmostEqual(density_weight(0.0), 0.0)
        self.assertAlmostEqual(density_weight(1.0), 0.0)
        self.assertAlmostEqual(density_weight(0.5), 1.0)
        # peak around 0.5
        self.assertGreater(density_weight(0.5), density_weight(0.25))
        self.assertGreater(density_weight(0.5), density_weight(0.75))

    def test_deterministic_seeding(self):
        cfg = GrainConfig(strength=GrainRoughness.STRONG, size=GrainSize.SMALL, seed=1234)
        a = GrainSynthesizer(cfg).generate_grain_pattern(8, 8)
        b = GrainSynthesizer(GrainConfig(strength=GrainRoughness.STRONG, size=GrainSize.SMALL, seed=1234)).generate_grain_pattern(8, 8)
        self.assertEqual(a, b)

    def test_buffer_application(self):
        for rough in (GrainRoughness.OFF, GrainRoughness.WEAK, GrainRoughness.STRONG):
            for size in (GrainSize.SMALL, GrainSize.LARGE):
                buf = bytearray([128] * (4 * 4))
                synth = GrainSynthesizer(GrainConfig(strength=rough, size=size, seed=7))
                out = synth.apply_to_buffer(buf, 4, 4, fmt="luma")
                self.assertEqual(len(out), 16)
        # rgb
        buf = bytearray([100, 150, 200] * (2 * 2))
        synth = GrainSynthesizer(GrainConfig(strength=GrainRoughness.STRONG, size=GrainSize.LARGE, seed=9))
        out = synth.apply_to_buffer(buf, 2, 2, fmt="rgb")
        self.assertEqual(len(out), 12)
        # OFF leaves buffer unchanged
        orig = bytearray([128] * 16)
        buf2 = bytearray(orig)
        GrainSynthesizer(GrainConfig(strength=GrainRoughness.OFF, seed=1)).apply_to_buffer(buf2, 4, 4, fmt="luma")
        self.assertEqual(bytes(buf2), bytes(orig))


if __name__ == "__main__":
    unittest.main()
