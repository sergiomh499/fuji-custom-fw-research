"""Tests for :mod:`core.wifi_patch`."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.wifi_patch import (
    ARM_NOP,
    WifiPatch,
    apply_defensive_patch,
    build_defensive_patch,
    detect_wifi_vulnerability,
    find_markers,
    identify_wifi_crash_sites,
    nop_at,
)


class TestWifiPatch(unittest.TestCase):
    def test_find_markers_synthetic(self):
        data = b"prefix tfDhcpdStart middle recv Memory Depletiion Err. suffix"
        markers = find_markers(data)
        self.assertIn("dhcpd_start", markers)
        self.assertIn("recv_memory_depletion", markers)
        self.assertEqual(len(markers["dhcpd_start"]), 1)

    def test_detect_vulnerable(self):
        data = b"lanInit efTcpIpInit tfDhcpdStart recv Memory Depletiion Err. STM AP_SOC Halt. IMPORT /guest DISCOVER 51541 51542"
        report = detect_wifi_vulnerability(data)
        self.assertTrue(report.vulnerable)
        self.assertEqual(report.missing, [])

    def test_detect_missing(self):
        report = detect_wifi_vulnerability(b"nothing here")
        self.assertFalse(report.vulnerable)
        self.assertTrue(report.missing)

    def test_identify_sites_sorted(self):
        data = b"DISCOVER" + b"\x00" + b"DISCOVER"
        sites = identify_wifi_crash_sites(data, {"discovery": b"DISCOVER"})
        self.assertEqual([s.offset for s in sites], [0, 9])

    def test_build_patch(self):
        data = b"abcd" + b"recv Memory Depletiion Err."
        ops = build_defensive_patch(data)
        self.assertTrue(ops)
        self.assertEqual(ops[0].new, ARM_NOP)

    def test_apply_patch(self):
        data = b"recv Memory Depletiion Err."
        ops = build_defensive_patch(data)
        patched = apply_defensive_patch(data, ops)
        self.assertNotEqual(patched, data)
        self.assertEqual(patched[:4], ARM_NOP)

    def test_nop_at(self):
        data = b"\x11\x22\x33\x44" + b"\x00" * 4
        patched = nop_at(data, 0, 4)
        self.assertEqual(patched[:4], ARM_NOP)

    def test_wifi_patch_class(self):
        data = b"lanInit efTcpIpInit tfDhcpdStart recv Memory Depletiion Err. STM AP_SOC Halt. IMPORT /guest DISCOVER 51541 51542"
        patcher = WifiPatch()
        report = patcher.detect(data)
        self.assertFalse(report.missing)
        ops = patcher.build(data)
        self.assertTrue(ops)
        patched = patcher.apply(data, ops)
        self.assertEqual(patched[:4], ARM_NOP)

    def test_actual_binary_if_present(self):
        binary = Path("/tmp/xt10_v131.bin")
        if not binary.exists():
            self.skipTest("X-T10 binary not available")
        data = binary.read_bytes()
        report = detect_wifi_vulnerability(data)
        self.assertTrue(report.vulnerable, report.missing)
        self.assertGreaterEqual(len(report.sites), 8)
        self.assertIn("dhcpd_start", report.markers)
        self.assertIn("recv_memory_depletion", report.markers)

    def test_patch_operation_precondition(self):
        from core.wifi_patch import WifiPatchOperation

        data = b"abcd"
        op = WifiPatchOperation(offset=0, old=b"abcd", new=ARM_NOP, reason="test")
        out = bytearray(data)
        op.apply(out)
        self.assertEqual(out[:4], ARM_NOP)
        with self.assertRaises(ValueError):
            op.apply(bytearray(b"zzzz"))


if __name__ == "__main__":
    unittest.main()
