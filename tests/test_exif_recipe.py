import io
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image

from core.exif_recipe import (
    Recipe,
    FujiMakerNoteReader,
    FujiMakerNoteWriter,
    read_recipe,
    write_recipe,
)


def _make_jpeg():
    img = Image.new("RGB", (4, 4), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestExifRecipe(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(Recipe))
        self.assertTrue(callable(FujiMakerNoteReader))
        self.assertTrue(callable(FujiMakerNoteWriter))

    def test_synthetic_jpeg_app1(self):
        data = _make_jpeg()
        r = Recipe(grain_effect=2, clarity=3, color_chrome_effect=1,
                   color_chrome_fx_blue=2, film_simulation=1, dynamic_range=200,
                   color=2, sharpness=1, noise_reduction=-1,
                   highlight=1, shadow=-1, wb_shift_r=2, wb_shift_b=-1)
        out = write_recipe(data, r)
        # APP1 present
        self.assertIn(b"Exif\x00\x00", out)
        self.assertTrue(out.startswith(b"\xff\xd8"))
        # image data not corrupted: SOS present
        self.assertIn(b"\xff\xda", out)
        # readable
        r2 = read_recipe(out)
        self.assertEqual(r2.grain_effect, 2)
        self.assertEqual(r2.clarity, 3)
        self.assertEqual(r2.color_chrome_effect, 1)

    def test_roundtrip(self):
        data = _make_jpeg()
        r = Recipe(film_simulation=3, dynamic_range=400, wb_mode=8, wb_kelvin=5500,
                   wb_shift_r=2, wb_shift_b=-2, highlight=2, shadow=-2, color=1,
                   sharpness=2, noise_reduction=-2, grain_effect=2,
                   color_chrome_effect=1, color_chrome_fx_blue=2, clarity=5,
                   name="TestRecipe")
        out = FujiMakerNoteWriter.write(data, r)
        r2 = FujiMakerNoteReader.read(out)
        self.assertEqual(r.film_simulation, r2.film_simulation)
        self.assertEqual(r.dynamic_range, r2.dynamic_range)
        self.assertEqual(r.wb_mode, r2.wb_mode)
        self.assertEqual(r.wb_shift_r, r2.wb_shift_r)
        self.assertEqual(r.wb_shift_b, r2.wb_shift_b)
        self.assertEqual(r.highlight, r2.highlight)
        self.assertEqual(r.shadow, r2.shadow)
        self.assertEqual(r.color, r2.color)
        self.assertEqual(r.sharpness, r2.sharpness)
        self.assertEqual(r.noise_reduction, r2.noise_reduction)
        self.assertEqual(r.grain_effect, r2.grain_effect)
        self.assertEqual(r.color_chrome_effect, r2.color_chrome_effect)
        self.assertEqual(r.color_chrome_fx_blue, r2.color_chrome_fx_blue)
        self.assertEqual(r.clarity, r2.clarity)

    def test_tag_extraction_grain_clarity_chrome(self):
        data = _make_jpeg()
        r = Recipe(grain_effect=1, clarity=-4, color_chrome_effect=2,
                   color_chrome_fx_blue=1)
        out = FujiMakerNoteWriter().write_jpeg(data, r)
        r2 = read_recipe(out)
        self.assertEqual(r2.grain_effect, 1)
        self.assertEqual(r2.clarity, -4)
        self.assertEqual(r2.color_chrome_effect, 2)
        self.assertEqual(r2.color_chrome_fx_blue, 1)

    def test_no_exif_creates_valid(self):
        # minimal JPEG without APP1
        data = _make_jpeg()
        # strip APP1? Just use raw SOI+SOS? Use full jpeg; remove exif by rewriting via writer on a tiff-less jpeg already no fuji. Test fallback path: create from bytes with no exif
        r = Recipe(clarity=1)
        out = write_recipe(data, r)
        self.assertEqual(read_recipe(out).clarity, 1)

    def test_aliases(self):
        r = Recipe(grain=2, color_chrome=1, color_chrome_blue=2, clarity=3,
                   white_balance=5, white_balance_fine_tune=(1, -1))
        self.assertEqual(r.grain_effect, 2)
        self.assertEqual(r.color_chrome_effect, 1)
        self.assertEqual(r.color_chrome_fx_blue, 2)
        self.assertEqual(r.clarity, 3)
        self.assertEqual(r.wb_mode, 5)
        self.assertEqual(r.wb_shift_r, 1)
        self.assertEqual(r.wb_shift_b, -1)


if __name__ == "__main__":
    unittest.main()
