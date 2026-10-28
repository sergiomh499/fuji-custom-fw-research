import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / "payloads" / "snap_focus"
BIN = SNAP_DIR / "snap_focus.bin"
CC = "arm-none-eabi-gcc"


class TestSnapFocus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which(CC) is None:
            raise unittest.SkipTest(f"{CC} not installed")

    def test_sources_exist(self):
        self.assertTrue((SNAP_DIR / "snap_focus.c").is_file())
        self.assertTrue((SNAP_DIR / "Makefile").is_file())
        self.assertTrue((SNAP_DIR / "Linker.ld").is_file())

    def test_make_builds_binary(self):
        subprocess.run(["make", "clean"], cwd=SNAP_DIR, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res = subprocess.run(["make"], cwd=SNAP_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(BIN.is_file())
        self.assertGreater(BIN.stat().st_size, 0)

    def test_binary_size_constraint(self):
        if not BIN.is_file():
            subprocess.run(["make"], cwd=SNAP_DIR, check=True)
        self.assertTrue(BIN.is_file())
        self.assertLessEqual(BIN.stat().st_size, 4096)
    def test_instruction_sanity(self):
        objdump = shutil.which("arm-none-eabi-objdump")
        self.assertIsNotNone(objdump)
        elf_file = SNAP_DIR / "snap_focus.elf"
        if not elf_file.is_file():
            subprocess.run(["make"], cwd=SNAP_DIR, check=True)
        res = subprocess.run([objdump, "-d", str(elf_file)],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        # ARM (not Thumb) instructions present
        self.assertIn("push", res.stdout)
        self.assertIn("pop", res.stdout)
        # Must reference the lens command constants
        src = (SNAP_DIR / "snap_focus.c").read_text()
        self.assertIn("CMD_LENS_MOVE_STEP", src)
        self.assertIn("LENS_SET_POSITION", src)


if __name__ == "__main__":
    unittest.main()
