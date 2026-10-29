import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.fp1 import FP1Converter
from core.recipe import Recipe


class TestFP1Import(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(FP1Converter))
        self.assertTrue(callable(FP1Converter.to_recipe))
        self.assertTrue(callable(FP1Converter.from_recipe))


class TestFP1Parsing(unittest.TestCase):
    def test_standard_snippet(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Profile>
  <FilmSimulation>Classic Chrome</FilmSimulation>
  <DynamicRange>DR400</DynamicRange>
  <WhiteBalance>Kelvin</WhiteBalance>
  <ColorTemperature>5500</ColorTemperature>
  <WBShiftR>2</WBShiftR>
  <WBShiftB>-1</WBShiftB>
  <HighlightTone>1</HighlightTone>
  <ShadowTone>-1</ShadowTone>
  <Color>2</Color>
  <Sharpness>1</Sharpness>
  <NoiseReduction>-2</NoiseReduction>
  <GrainEffect>Weak</GrainEffect>
</Profile>"""
        r = FP1Converter.to_recipe(xml)
        self.assertEqual(r.film_simulation_name, "Classic Chrome")
        self.assertEqual(r.dynamic_range, 400)
        self.assertEqual(r.wb_mode_name, "kelvin")
        self.assertEqual(r.wb_kelvin, 5500)
        self.assertEqual(r.wb_shift_r, 2)
        self.assertEqual(r.wb_shift_b, -1)
        self.assertEqual(r.highlight, 1)
        self.assertEqual(r.shadow, -1)
        self.assertEqual(r.color, 2)
        self.assertEqual(r.sharpness, 1)
        self.assertEqual(r.noise_reduction, -2)

    def test_instance_method(self):
        conv = FP1Converter()
        xml = "<Profile><FilmSimulation>Velvia</FilmSimulation></Profile>"
        r = conv.to_recipe(xml)
        self.assertEqual(r.film_simulation_name, "Velvia")

    def test_file_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.fp1"
            p.write_text("<Profile><FilmSimulation>Astia</FilmSimulation></Profile>", encoding="utf-8")
            r = FP1Converter.to_recipe(str(p))
            self.assertEqual(r.film_simulation_name, "Astia")


class TestFP1RoundTrip(unittest.TestCase):
    def test_roundtrip(self):
        r = Recipe(name="RT", film_simulation="Acros", dynamic_range=200,
                   wb_mode="daylight", wb_kelvin=6000, wb_shift_r=1, wb_shift_b=2,
                   highlight=-2, shadow=2, color=0, sharpness=-1, noise_reduction=1)
        xml = FP1Converter.from_recipe(r)
        r2 = FP1Converter.to_recipe(xml)
        self.assertEqual(r.film_simulation, r2.film_simulation)
        self.assertEqual(r.dynamic_range, r2.dynamic_range)
        self.assertEqual(r.wb_kelvin, r2.wb_kelvin)
        self.assertEqual(r.highlight, r2.highlight)
        self.assertEqual(r.shadow, r2.shadow)
        self.assertEqual(r.color, r2.color)
        self.assertEqual(r.sharpness, r2.sharpness)
        self.assertEqual(r.noise_reduction, r2.noise_reduction)


class TestFP1Malformed(unittest.TestCase):
    def test_unexpected_tags(self):
        xml = "<Profile><Foo>bar</Foo><Baz>123</Baz></Profile>"
        r = FP1Converter.to_recipe(xml)
        self.assertIsInstance(r, Recipe)

    def test_malformed_xml_raises(self):
        with self.assertRaises(ValueError):
            FP1Converter.to_recipe("<not xml")

    def test_invalid_values_ignored(self):
        xml = """<Profile>
  <FilmSimulation>NotARealSim</FilmSimulation>
  <WBShiftR>99</WBShiftR>
  <Color>99</Color>
</Profile>"""
        r = FP1Converter.to_recipe(xml)
        self.assertEqual(r.wb_shift_r, 0)
        self.assertEqual(r.color, 0)


if __name__ == "__main__":
    unittest.main()
