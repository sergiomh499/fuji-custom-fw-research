import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.recipe import Recipe, RecipeSerializer, RecipeBank, FILM_SIMULATIONS


class TestRecipe(unittest.TestCase):
    def test_import(self):
        self.assertTrue(callable(Recipe))
        self.assertTrue(callable(RecipeSerializer))
        self.assertTrue(callable(RecipeBank))

    def test_validation_ranges(self):
        with self.assertRaises(ValueError):
            Recipe(highlight=5)
        with self.assertRaises(ValueError):
            Recipe(dynamic_range=150)
        with self.assertRaises(ValueError):
            Recipe(wb_kelvin=1000)

    def test_film_sim_name(self):
        r = Recipe(film_simulation="Classic Chrome")
        self.assertEqual(r.film_simulation, 3)
        self.assertEqual(r.film_simulation_name, "Classic Chrome")

    def test_binary_roundtrip(self):
        r = Recipe(name="Test", slot="C2", film_simulation=1, dynamic_range=200,
                   wb_mode="kelvin", wb_kelvin=5500, wb_shift_r=2, wb_shift_b=-1,
                   highlight=1, shadow=-1, color=2, sharpness=1, noise_reduction=-2)
        data = RecipeSerializer.to_bytes(r)
        self.assertEqual(len(data), 128)
        r2 = RecipeSerializer.from_bytes(data)
        self.assertEqual(r.name, r2.name)
        self.assertEqual(r.slot, r2.slot)
        self.assertEqual(r.film_simulation, r2.film_simulation)
        self.assertEqual(r.dynamic_range, r2.dynamic_range)
        self.assertEqual(r.wb_mode, r2.wb_mode)
        self.assertEqual(r.wb_kelvin, r2.wb_kelvin)
        self.assertEqual(r.wb_shift_r, r2.wb_shift_r)
        self.assertEqual(r.wb_shift_b, r2.wb_shift_b)
        self.assertEqual(r.highlight, r2.highlight)
        self.assertEqual(r.shadow, r2.shadow)
        self.assertEqual(r.color, r2.color)
        self.assertEqual(r.sharpness, r2.sharpness)
        self.assertEqual(r.noise_reduction, r2.noise_reduction)

    def test_corrupted_magic(self):
        r = Recipe()
        data = bytearray(RecipeSerializer.to_bytes(r))
        data[0:4] = b"XXXX"
        with self.assertRaises(ValueError):
            RecipeSerializer.from_bytes(bytes(data))

    def test_corrupted_checksum(self):
        r = Recipe()
        data = bytearray(RecipeSerializer.to_bytes(r))
        data[124] ^= 0xFF
        with self.assertRaises(ValueError):
            RecipeSerializer.from_bytes(bytes(data))

    def test_truncated(self):
        with self.assertRaises(ValueError):
            RecipeSerializer.from_bytes(b"\x00" * 10)

    def test_text_roundtrip(self):
        r = Recipe(name="MyRec", slot="C1", film_simulation="Velvia", dynamic_range=400,
                   wb_mode=8, wb_kelvin=6000, wb_shift_r=1, wb_shift_b=2,
                   highlight=-2, shadow=2, color=0, sharpness=-1, noise_reduction=1)
        text = RecipeSerializer.to_text(r)
        r2 = RecipeSerializer.from_text(text)
        self.assertEqual(r.name, r2.name)
        self.assertEqual(r.film_simulation, r2.film_simulation)
        self.assertEqual(r.dynamic_range, r2.dynamic_range)
        self.assertEqual(r.wb_kelvin, r2.wb_kelvin)
        self.assertEqual(r.highlight, r2.highlight)

    def test_text_without_section(self):
        text = "name = Foo\nfilm_simulation = 0\ndynamic_range = 100\n"
        r = RecipeSerializer.from_text(text)
        self.assertEqual(r.name, "Foo")

    def test_bank_slots(self):
        bank = RecipeBank()
        r = Recipe(name="R1")
        bank.set_slot("C1", r)
        self.assertIs(bank.get_slot("C1"), r)
        bank.delete_slot("C1")
        self.assertIsNone(bank.get_slot(1))

    def test_bank_sd_export_import(self):
        with tempfile.TemporaryDirectory() as td:
            bank = RecipeBank()
            bank.set_slot(1, Recipe(name="Exported", film_simulation="Astia"))
            out = bank.export_sd(td)
            self.assertTrue((out / "C1.fujirecipe").exists())
            bank2 = RecipeBank()
            n = bank2.import_sd(td)
            self.assertGreaterEqual(n, 1)
            self.assertEqual(bank2.get_slot("C1").name, "Exported")

    def test_builtin_recipes(self):
        bank = RecipeBank()
        bank.load_builtin_recipes()
        self.assertEqual(bank["C1"].name, "Kodachrome 64")
        self.assertEqual(bank["C2"].name, "Portra 400")
        self.assertEqual(bank["C3"].name, "CineStill 800T")
        self.assertEqual(bank["C4"].name, "Tri-X 400")
        self.assertEqual(bank["C5"].name, "Fuji Superia 400")
        self.assertEqual(bank["C6"].name, "Ilford HP5 Plus")
        self.assertEqual(bank["C7"].name, "Velvia Landscape")
        # Verify per-recipe decoupled white balance shifts
        self.assertEqual(bank["C1"].wb_shift_r, 2)
        self.assertEqual(bank["C1"].wb_shift_b, -4)
        self.assertEqual(bank["C2"].wb_shift_b, -5)

    def test_aliases(self):
        r = Recipe()
        data = RecipeSerializer.serialize(r)
        r2 = RecipeSerializer.deserialize(data)
        self.assertEqual(r.name, r2.name)
        text = RecipeSerializer.dumps(r)
        r3 = RecipeSerializer.loads(text)
        self.assertEqual(r.name, r3.name)

    def test_is_valid(self):
        r = Recipe()
        data = RecipeSerializer.to_bytes(r)
        self.assertTrue(RecipeSerializer.is_valid(data))
        self.assertFalse(RecipeSerializer.is_valid(b"\x00" * 128))


if __name__ == "__main__":
    unittest.main()
