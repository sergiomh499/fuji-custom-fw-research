import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OSD_DIR = ROOT / "payloads" / "osd_overlay"
BIN = OSD_DIR / "osd_overlay.bin"
CC = "arm-none-eabi-gcc"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.osd import (
    OSDFramebuffer,
    WIDTH,
    HEIGHT,
    BUFFER_SIZE,
    OSD_DEBUG_ROUTINE,
    DISPLAY_BUFFER_PTR,
    rgb565,
    zebra_stripe,
    peaking_highlight,
)


class TestOSD(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(WIDTH, 640)
        self.assertEqual(HEIGHT, 480)
        self.assertEqual(BUFFER_SIZE, 307200)
        self.assertEqual(OSD_DEBUG_ROUTINE, 0x007F9C1C)
        self.assertEqual(DISPLAY_BUFFER_PTR, 0x01B59BD4)

    def test_rgb565_encoding(self):
        # pure red
        self.assertEqual(rgb565(255, 0, 0), 0xF800)
        # pure green
        self.assertEqual(rgb565(0, 255, 0), 0x07E0)
        # pure blue
        self.assertEqual(rgb565(0, 0, 255), 0x001F)
        # black
        self.assertEqual(rgb565(0, 0, 0), 0)

    def test_framebuffer_size(self):
        fb = OSDFramebuffer()
        self.assertEqual(len(fb.buffer), BUFFER_SIZE)
        self.assertEqual(len(fb.buffer), WIDTH * HEIGHT)

    def test_grid_rendering(self):
        fb = OSDFramebuffer()
        fb.clear(0)
        fb.draw_framing_guides("thirds")
        # thirds lines should have nonzero pixels
        self.assertGreater(fb.get_pixel(WIDTH // 3, HEIGHT // 2), 0)
        self.assertGreater(fb.get_pixel(2 * WIDTH // 3, HEIGHT // 2), 0)
        self.assertGreater(fb.get_pixel(WIDTH // 2, HEIGHT // 3), 0)

        # Test XPan 65:24
        fb.clear(0)
        fb.draw_framing_guides("65:24")
        self.assertGreater(fb.get_pixel(WIDTH // 2, 0), 0)

        # Test 1:1 Square
        fb.clear(0)
        fb.draw_framing_guides("1:1")
        self.assertGreater(fb.get_pixel(0, HEIGHT // 2), 0)
    def test_zebra_calculation(self):
        self.assertTrue(zebra_stripe(10, 10, 250, threshold=235))
        self.assertFalse(zebra_stripe(10, 10, 100, threshold=235))
        # alternating bands
        self.assertNotEqual(
            zebra_stripe(0, 0, 250, threshold=235, stripe=4),
            zebra_stripe(0, 4, 250, threshold=235, stripe=4),
        )

    def test_peaking_calculation(self):
        self.assertTrue(peaking_highlight(50, threshold=40))
        self.assertFalse(peaking_highlight(10, threshold=40))

    def test_zebra_draw(self):
        fb = OSDFramebuffer()
        fb.clear(0)
        fb.draw_zebra(threshold=0, luma=255)
        # some pixels set
        self.assertTrue(any(b != 0 for b in fb.buffer))

    def test_status_bar(self):
        fb = OSDFramebuffer()
        fb.clear(0)
        fb.draw_status_bar(battery_voltage=7.4, sensor_temp=42.0)
        self.assertTrue(any(b != 0 for b in fb.buffer[:WIDTH]))

    def test_sources_exist(self):
        self.assertTrue((OSD_DIR / "osd_overlay.c").is_file())
        self.assertTrue((OSD_DIR / "Makefile").is_file())
        self.assertTrue((OSD_DIR / "Linker.ld").is_file())

    def test_mitigation_links_present(self):
        src = (OSD_DIR / "osd_overlay.c").read_text()
        self.assertIn("docs/BRICK_ANALYSIS_AND_RECOVERY.md#cold-hooking", src)
        core_src = (ROOT / "core" / "osd.py").read_text()
        self.assertIn("docs/BRICK_ANALYSIS_AND_RECOVERY.md#cold-hooking", core_src)

    @unittest.skipUnless(shutil.which(CC), f"{CC} not installed")
    def test_make_builds_binary(self):
        subprocess.run(["make", "clean"], cwd=OSD_DIR, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res = subprocess.run(["make"], cwd=OSD_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(BIN.is_file())
        self.assertGreater(BIN.stat().st_size, 0)

    @unittest.skipUnless(shutil.which(CC), f"{CC} not installed")
    def test_binary_size_constraint(self):
        if not BIN.is_file():
            subprocess.run(["make"], cwd=OSD_DIR, check=True)
        self.assertTrue(BIN.is_file())
        self.assertLessEqual(BIN.stat().st_size, 8192)


if __name__ == "__main__":
    unittest.main()
