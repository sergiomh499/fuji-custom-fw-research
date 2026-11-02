import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.xapp_protocol import (
    XAppPacket, XAppMessageType, XAppGeotagPayload, XAppActivityLogger,
    XAppSession, XAppSessionState, crc16_ccitt, XAppCRCError, XAppFramingError,
)


class TestCRC(unittest.TestCase):
    def test_crc_deterministic(self):
        self.assertEqual(crc16_ccitt(b"123456789"), crc16_ccitt(b"123456789"))

    def test_crc_changes(self):
        self.assertNotEqual(crc16_ccitt(b"abc"), crc16_ccitt(b"abd"))


class TestPacket(unittest.TestCase):
    def test_roundtrip(self):
        p = XAppPacket(XAppMessageType.STATUS, seq=7, payload=b"\x01\x02\x03")
        raw = p.pack()
        u = XAppPacket.unpack(raw)
        self.assertEqual(u.msg_type, XAppMessageType.STATUS)
        self.assertEqual(u.seq, 7)
        self.assertEqual(u.payload, b"\x01\x02\x03")
        self.assertTrue(u.verify())

    def test_corrupted_rejected(self):
        p = XAppPacket(XAppMessageType.GEOTAG, seq=1, payload=b"hello")
        raw = bytearray(p.pack())
        raw[-1] ^= 0xFF
        with self.assertRaises((XAppCRCError, ValueError)):
            XAppPacket.unpack(bytes(raw))

    def test_truncated_rejected(self):
        with self.assertRaises((XAppFramingError, ValueError)):
            XAppPacket.unpack(b"\xfa\xce\x01")

    def test_bad_sync_rejected(self):
        p = XAppPacket(XAppMessageType.STATUS, seq=1, payload=b"x")
        raw = bytearray(p.pack())
        raw[0] = 0x00
        with self.assertRaises((XAppFramingError, ValueError)):
            XAppPacket.unpack(bytes(raw))

    def test_all_message_types(self):
        for mt in XAppMessageType:
            p = XAppPacket(mt, seq=2, payload=b"")
            u = XAppPacket.unpack(p.pack())
            self.assertEqual(u.msg_type, mt)


class TestGeotag(unittest.TestCase):
    def test_scaled_roundtrip(self):
        g = XAppGeotagPayload(latitude=35.6895, longitude=139.6917, altitude=40.0, timestamp=1700000000)
        raw = g.pack()
        u = XAppGeotagPayload.unpack(raw)
        self.assertAlmostEqual(u.latitude, g.latitude, places=6)
        self.assertAlmostEqual(u.longitude, g.longitude, places=6)
        self.assertAlmostEqual(u.altitude, g.altitude, places=0)
        self.assertEqual(u.timestamp, g.timestamp)

    def test_float_roundtrip(self):
        g = XAppGeotagPayload(latitude=1.23456789, longitude=-9.87654321, altitude=123.45, timestamp=42, mode="float")
        raw = g.pack()
        u = XAppGeotagPayload.unpack(raw, mode="float")
        self.assertAlmostEqual(u.latitude, g.latitude, places=12)
        self.assertAlmostEqual(u.longitude, g.longitude, places=12)
        self.assertAlmostEqual(u.altitude, g.altitude, places=5)
        self.assertEqual(u.timestamp, g.timestamp)

    def test_alias_access(self):
        g = XAppGeotagPayload(lat=1.0, lon=2.0, alt=3.0, ts=4)
        self.assertEqual(g.lat, 1.0)
        self.assertEqual(g.lon, 2.0)
        self.assertEqual(g.alt, 3.0)
        self.assertEqual(g.ts, 4)


class TestActivity(unittest.TestCase):
    def test_aggregation(self):
        a = XAppActivityLogger()
        a.increment_shutter("Velvia")
        a.increment_shutter("Velvia")
        a.increment_shutter("Provia")
        a.increment_shutter()  # no sim
        self.assertEqual(a.shutter_count, 4)
        self.assertEqual(a.film_simulation_counts["Velvia"], 2)
        self.assertEqual(a.film_simulation_counts["Provia"], 1)

    def test_roundtrip_bytes(self):
        a = XAppActivityLogger()
        a.increment_shutter("Acros", 3)
        b = a.to_bytes()
        c = XAppActivityLogger.from_bytes(b)
        self.assertEqual(c.shutter_count, 3)
        self.assertEqual(c.film_simulation_counts["Acros"], 3)

    def test_alias_methods(self):
        a = XAppActivityLogger()
        a.record_shot("Sepia")
        a.log_shot("Sepia")
        self.assertEqual(a.total_shutters, 2)
        self.assertEqual(a.film_sim_counts["Sepia"], 2)


class TestSession(unittest.TestCase):
    def test_state_transitions(self):
        s = XAppSession()
        self.assertEqual(s.state, XAppSessionState.UNPAIRED)
        s.start_pairing()
        self.assertEqual(s.state, XAppSessionState.PAIRING)
        s.complete_pairing()
        self.assertEqual(s.state, XAppSessionState.CONNECTED)
        s.begin_transfer()
        self.assertEqual(s.state, XAppSessionState.TRANSFERRING)
        s.end_transfer()
        self.assertEqual(s.state, XAppSessionState.IDLE)

    def test_pairing_handshake(self):
        s = XAppSession()
        req = s.pair_request()
        self.assertEqual(req.msg_type, XAppMessageType.PAIR_REQ)
        resp = s.pair_response(req.payload)
        u = XAppPacket.unpack(resp.pack())
        self.assertEqual(u.msg_type, XAppMessageType.PAIR_RESP)

    def test_handle_packet(self):
        s = XAppSession()
        req = XAppPacket(XAppMessageType.PAIR_REQ, payload=b"\x01\x02")
        s.handle_packet(req)
        self.assertEqual(s.state, XAppSessionState.PAIRING)
        resp = XAppPacket(XAppMessageType.PAIR_RESP, payload=b"\x03\x04")
        s.handle_packet(resp)
        self.assertEqual(s.state, XAppSessionState.CONNECTED)


if __name__ == "__main__":
    unittest.main()
