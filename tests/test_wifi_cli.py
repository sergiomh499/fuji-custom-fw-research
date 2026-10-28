"""Tests for the ``fujitool patch wifi`` CLI command."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUJITOOL = ROOT / "fujitool"

sys.path.insert(0, str(ROOT))


class TestWifiCli(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(FUJITOOL), *args],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )

    def test_help_shows_mitigation_link(self):
        res = self._run("patch", "wifi", "--help")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery", res.stdout + res.stderr)

    def test_patch_synthetic_binary(self):
        data = b"lanInit efTcpIpInit tfDhcpdStart recv Memory Depletiion Err. STM AP_SOC Halt. IMPORT /guest DISCOVER 51541 51542"
        inp = ROOT / "tests" / "_tmp_wifi_synth.bin"
        out = ROOT / "tests" / "_tmp_wifi_synth_out.bin"
        try:
            inp.write_bytes(data)
            res = self._run("patch", "wifi", str(inp), str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(out.exists())
            self.assertEqual(len(out.read_bytes()), len(data))
            self.assertNotEqual(out.read_bytes(), data)
        finally:
            for p in (inp, out):
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass

    @unittest.skipUnless(Path("/tmp/xt10_v131.bin").exists(), "firmware not present")
    def test_patch_actual_firmware_header(self):
        inp = Path("/tmp/xt10_v131.bin")
        out = ROOT / "tests" / "_tmp_wifi_xt10_out.bin"
        try:
            res = self._run("patch", "wifi", str(inp), str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(out.exists())
            self.assertEqual(len(out.read_bytes()), len(inp.read_bytes()))
        finally:
            try:
                out.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()