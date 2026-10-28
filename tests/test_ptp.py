"""Tests for :mod:`core.ptp`."""

import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ptp import (
    PTPContainer,
    PTPClient,
    LoopbackTransport,
    CONTAINER_COMMAND,
    CONTAINER_DATA,
    CONTAINER_RESPONSE,
    CONTAINER_EVENT,
    OP_READ_MEMORY,
    OP_WRITE_MEMORY,
    RESPONSE_OK,
    FIRM_PTP,
    DRAM_STAGING,
    PTP_MITIGATION,
    PTPError,
)


class TestPTPContainer(unittest.TestCase):
    def test_pack_unpack_command(self):
        c = PTPContainer(CONTAINER_COMMAND, OP_READ_MEMORY, transaction_id=42, params=[0x1000, 0x10])
        raw = c.pack()
        u = PTPContainer.unpack(raw)
        self.assertEqual(u.type, CONTAINER_COMMAND)
        self.assertEqual(u.code, OP_READ_MEMORY)
        self.assertEqual(u.transaction_id, 42)
        self.assertEqual(u.params, [0x1000, 0x10])

    def test_pack_unpack_data(self):
        payload = b"\x01\x02\x03\x04"
        c = PTPContainer(CONTAINER_DATA, OP_READ_MEMORY, transaction_id=7, data=payload)
        u = PTPContainer.unpack(c.pack())
        self.assertEqual(u.type, CONTAINER_DATA)
        self.assertEqual(u.data, payload)

    def test_pack_unpack_response(self):
        c = PTPContainer(CONTAINER_RESPONSE, RESPONSE_OK, transaction_id=9, params=[0])
        u = PTPContainer.unpack(c.pack())
        self.assertEqual(u.type, CONTAINER_RESPONSE)
        self.assertEqual(u.code, RESPONSE_OK)

    def test_event_type(self):
        c = PTPContainer(CONTAINER_EVENT, 0xC001, transaction_id=1)
        u = PTPContainer.unpack(c.pack())
        self.assertEqual(u.type, CONTAINER_EVENT)

    def test_truncated_raises_mitigation(self):
        with self.assertRaises(PTPError) as ctx:
            PTPContainer.unpack(b"\x00" * 4)
        self.assertIn("ptp-ram-recovery", str(ctx.exception))


class TestPTPClient(unittest.TestCase):
    def setUp(self):
        self.transport = LoopbackTransport()
        # seed memory
        self.transport._write(DRAM_STAGING, b"HELLO" + b"\x00" * 10)
        self.client = PTPClient(self.transport)

    def test_read_memory(self):
        data = self.client.read_memory(DRAM_STAGING, 5)
        self.assertEqual(data, b"HELLO")

    def test_write_memory(self):
        self.client.write_memory(DRAM_STAGING + 20, b"WORLD")
        data = self.client.read_memory(DRAM_STAGING + 20, 5)
        self.assertEqual(data, b"WORLD")

    def test_dump_ram(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "dump.bin")
            self.client.dump_ram(out, start_addr=DRAM_STAGING, size=8)
            self.assertEqual(Path(out).read_bytes(), b"HELLO\x00\x00\x00")

    def test_error_mitigation_message(self):
        # force failure by corrupting response? Instead check PTPError text contains link
        err = PTPError("boom")
        self.assertIn("ptp-ram-recovery", str(err))
        # ensure mitigation constant present
        self.assertIn("ptp-ram-recovery", PTP_MITIGATION)

    def test_constants(self):
        self.assertEqual(FIRM_PTP, 0x01E7C718)
        self.assertEqual(DRAM_STAGING, 0x01CF0000)


class TestCommandGeneration(unittest.TestCase):
    def test_read_command_container(self):
        t = LoopbackTransport()
        client = PTPClient(t)
        client.read_memory(0x1234, 8)
        # first sent is command
        first = PTPContainer.unpack(t.sent[0])
        self.assertEqual(first.type, CONTAINER_COMMAND)
        self.assertEqual(first.code, OP_READ_MEMORY)
        self.assertEqual(first.params, [0x1234, 8])


if __name__ == "__main__":
    unittest.main()
