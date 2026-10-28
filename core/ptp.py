"""Picture Transfer Protocol (PTP / ISO 15740) framing and USB client.

Mitigation (volatile RAM only): docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
DRAM is 100% volatile; power-cycling clears hung execution immediately (0% flash risk).
"""

import collections
import struct
from typing import Any, Optional

MITIGATION_LINK = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery"

PTP_MITIGATION = (
    "Mitigation: DRAM is 100% volatile; pull the battery for 30s to clear any hung "
    "execution immediately (0% flash risk). See " + MITIGATION_LINK
)

# Container types
CONTAINER_COMMAND = 1
CONTAINER_DATA = 2
CONTAINER_RESPONSE = 3
CONTAINER_EVENT = 4

CONTAINER_TYPE_NAMES = {
    CONTAINER_COMMAND: "Command",
    CONTAINER_DATA: "Data",
    CONTAINER_RESPONSE: "Response",
    CONTAINER_EVENT: "Event",
}

# Standard response codes
RESPONSE_OK = 0x2001
RESPONSE_GENERAL_ERROR = 0x2002
RESPONSE_DEVICE_BUSY = 0x2019

# Standard opcodes (commonly used)
OP_GET_DEVICE_INFO = 0x1001
OP_OPEN_SESSION = 0x1002
OP_CLOSE_SESSION = 0x1003

# Fuji vendor opcodes
OP_READ_MEMORY = 0x9028
OP_WRITE_MEMORY = 0x9029
OP_EXEC_CODE = 0x902A

FUJI_VENDOR_OPCODES = {
    OP_READ_MEMORY: "ReadMemory",
    OP_WRITE_MEMORY: "WriteMemory",
    OP_EXEC_CODE: "ExecCode",
}

# Target addresses for X-T10 v1.31
FIRM_PTP = 0x01E7C718
DRAM_STAGING = 0x01CF0000
DRAM_STAGING_END = 0x01CF4000

HEADER_SIZE = 12  # length(4) + type(2) + code(2) + transaction_id(4)


class PTPError(Exception):
    """PTP transport/protocol error.

    Mitigation: DRAM is 100% volatile; power-cycle clears hung execution.
    See docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
    """

    def __init__(self, message=""):
        if MITIGATION_LINK not in str(message):
            message = f"{message} {PTP_MITIGATION}" if message else PTP_MITIGATION
        super().__init__(message)


class PTPContainer:
    """PTP container (ISO 15740)."""

    def __init__(self, cont_type, code, transaction_id=0, params=None, data=b""):
        self.type = cont_type
        self.code = code
        self.transaction_id = transaction_id
        self.params = list(params or [])
        self.data = bytes(data or b"")

    def pack(self) -> bytes:
        if self.type == CONTAINER_COMMAND:
            payload = b"".join(struct.pack("<I", p) for p in self.params)
        elif self.type == CONTAINER_DATA:
            payload = self.data
        elif self.type == CONTAINER_RESPONSE:
            payload = b"".join(struct.pack("<I", p) for p in self.params)
        elif self.type == CONTAINER_EVENT:
            payload = b"".join(struct.pack("<I", p) for p in self.params)
        else:
            payload = self.data
        total = HEADER_SIZE + len(payload)
        header = struct.pack("<IHHI", total, self.type, self.code, self.transaction_id)
        return header + payload

    @classmethod
    def unpack(cls, raw: bytes) -> "PTPContainer":
        if len(raw) < HEADER_SIZE:
            raise PTPError("truncated PTP container; " + PTP_MITIGATION)
        total, cont_type, code, tid = struct.unpack("<IHHI", raw[:HEADER_SIZE])
        body = raw[HEADER_SIZE:total]
        if cont_type == CONTAINER_DATA:
            return cls(cont_type, code, tid, params=[], data=body)
        # command/response/event: params as uint32
        n = len(body) // 4
        params = list(struct.unpack("<" + "I" * n, body[: n * 4])) if n else []
        return cls(cont_type, code, tid, params=params, data=b"")

    @property
    def type_name(self) -> str:
        return CONTAINER_TYPE_NAMES.get(self.type, "Unknown")


def _try_usb():
    try:
        import usb.core  # noqa: F401
        import usb.util  # noqa: F401
        return True
    except Exception:
        return False


class Transport:
    def send(self, data: bytes) -> None:
        raise NotImplementedError

    def recv(self, timeout: Optional[float] = None) -> bytes:
        raise NotImplementedError


class LoopbackTransport(Transport):
    """In-memory transport simulating a Fuji device with readable/writable DRAM.

    Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
    """

    def __init__(self, memory_size: int = 0x2000000):
        self.memory = bytearray(memory_size)
        # base address for the simulated DRAM window
        self.base = 0x01000000
        self._rx = collections.deque()
        self._pending_write_addr = None
        self._pending_write_len = None
        self.sent = []

    def _addr_to_offset(self, addr):
        return addr - self.base

    def _read(self, addr, length):
        off = self._addr_to_offset(addr)
        out = bytearray(length)
        for i in range(length):
            idx = off + i
            if 0 <= idx < len(self.memory):
                out[i] = self.memory[idx]
            else:
                out[i] = 0
        return bytes(out)

    def _write(self, addr, data):
        off = self._addr_to_offset(addr)
        for i, b in enumerate(data):
            idx = off + i
            if 0 <= idx < len(self.memory):
                self.memory[idx] = b

    def send(self, data: bytes) -> None:
        self.sent.append(data)
        c = PTPContainer.unpack(data)
        if c.type == CONTAINER_COMMAND and c.code == OP_READ_MEMORY:
            addr = c.params[0]
            length = c.params[1]
            chunk = self._read(addr, length)
            dc = PTPContainer(CONTAINER_DATA, c.code, c.transaction_id, data=chunk)
            self._rx.append(dc.pack())
            rc = PTPContainer(CONTAINER_RESPONSE, RESPONSE_OK, c.transaction_id, params=[0])
            self._rx.append(rc.pack())
        elif c.type == CONTAINER_COMMAND and c.code == OP_WRITE_MEMORY:
            self._pending_write_addr = c.params[0]
            self._pending_write_len = c.params[1] if len(c.params) > 1 else 0
        elif c.type == CONTAINER_DATA and c.code == OP_WRITE_MEMORY:
            addr = self._pending_write_addr
            if addr is None:
                raise PTPError("write data without pending command; " + PTP_MITIGATION)
            self._write(addr, c.data)
            rc = PTPContainer(CONTAINER_RESPONSE, RESPONSE_OK, c.transaction_id, params=[0])
            self._rx.append(rc.pack())
            self._pending_write_addr = None
        elif c.type == CONTAINER_COMMAND and c.code == OP_EXEC_CODE:
            rc = PTPContainer(CONTAINER_RESPONSE, RESPONSE_OK, c.transaction_id, params=[0])
            self._rx.append(rc.pack())
        else:
            rc = PTPContainer(CONTAINER_RESPONSE, RESPONSE_OK, c.transaction_id, params=[0])
            self._rx.append(rc.pack())

    def recv(self, timeout=None) -> bytes:
        if not self._rx:
            raise PTPError("no response available; " + PTP_MITIGATION)
        return self._rx.popleft()


class USBTransport(Transport):
    """pyusb-backed transport (optional)."""

    def __init__(self, vendor_id=None, product_id=None):
        if not _try_usb():
            raise PTPError("pyusb not available; " + PTP_MITIGATION)
        import usb.core
        import usb.util
        self.usb = usb.core
        self.util = usb.util
        dev = usb.core.find(idVendor=vendor_id, idProduct=product_id) if vendor_id else usb.core.find()
        if dev is None:
            raise PTPError("no USB device found; " + PTP_MITIGATION)
        self.dev = dev
        # claim first interface
        cfg = dev.get_active_configuration()
        self.intf = cfg[(0, 0)]
        usb.util.claim_interface(dev, self.intf)
        self.ep_out = usb.util.find_descriptor(self.intf, custom_match=lambda e: (e.bEndpointAddress & 0x80) == 0)
        self.ep_in = usb.util.find_descriptor(self.intf, custom_match=lambda e: (e.bEndpointAddress & 0x80) != 0)

    def send(self, data: bytes) -> None:
        self.ep_out.write(data)

    def recv(self, timeout=None) -> bytes:
        t = timeout or 5000
        return bytes(self.ep_in.read(1024 * 1024, timeout=t))


class PTPClient:
    """PTP client over a transport.

    Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
    """

    def __init__(self, transport: Optional[Transport] = None):
        if transport is None:
            if _try_usb():
                transport = USBTransport()
            else:
                transport = LoopbackTransport()
        self.transport = transport
        self._tid = 0

    def _next_tid(self):
        self._tid = (self._tid + 1) & 0xFFFFFFFF
        return self._tid

    def read_memory(self, address: int, length: int) -> bytes:
        """Read `length` bytes from `address`.

        Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
        """
        if length < 0:
            raise PTPError("negative length; " + PTP_MITIGATION)
        tid = self._next_tid()
        cmd = PTPContainer(CONTAINER_COMMAND, OP_READ_MEMORY, tid, params=[address, length])
        self.transport.send(cmd.pack())
        data_raw = self.transport.recv()
        data_c = PTPContainer.unpack(data_raw)
        if data_c.type != CONTAINER_DATA:
            raise PTPError("expected data container; " + PTP_MITIGATION)
        resp_raw = self.transport.recv()
        resp_c = PTPContainer.unpack(resp_raw)
        if resp_c.type != CONTAINER_RESPONSE or resp_c.code != RESPONSE_OK:
            raise PTPError(f"read_memory failed (0x{resp_c.code:04x}); " + PTP_MITIGATION)
        return data_c.data

    def write_memory(self, address: int, data: bytes) -> bool:
        """Write `data` to `address`.

        Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
        """
        data = bytes(data)
        tid = self._next_tid()
        cmd = PTPContainer(CONTAINER_COMMAND, OP_WRITE_MEMORY, tid, params=[address, len(data)])
        self.transport.send(cmd.pack())
        dc = PTPContainer(CONTAINER_DATA, OP_WRITE_MEMORY, tid, data=data)
        self.transport.send(dc.pack())
        resp_raw = self.transport.recv()
        resp_c = PTPContainer.unpack(resp_raw)
        if resp_c.type != CONTAINER_RESPONSE or resp_c.code != RESPONSE_OK:
            raise PTPError(f"write_memory failed (0x{resp_c.code:04x}); " + PTP_MITIGATION)
        return True

    def exec_code(self, address: int) -> bool:
        """Execute code at `address` (Fuji vendor opcode 0x902A).

        Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
        """
        tid = self._next_tid()
        cmd = PTPContainer(CONTAINER_COMMAND, OP_EXEC_CODE, tid, params=[address])
        self.transport.send(cmd.pack())
        resp_raw = self.transport.recv()
        resp_c = PTPContainer.unpack(resp_raw)
        if resp_c.type != CONTAINER_RESPONSE or resp_c.code != RESPONSE_OK:
            raise PTPError(f"exec_code failed (0x{resp_c.code:04x}); " + PTP_MITIGATION)
        return True

    def dump_ram(self, output_path: str, start_addr: int = DRAM_STAGING, size: int = 0x4000, chunk: int = 0x400) -> str:
        """Dump `size` bytes from `start_addr` to `output_path`.

        Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
        """
        out = bytearray()
        addr = start_addr
        remaining = size
        while remaining > 0:
            n = min(chunk, remaining)
            out += self.read_memory(addr, n)
            addr += n
            remaining -= n
        with open(output_path, "wb") as f:
            f.write(out)
        return output_path
