#!/usr/bin/env python3
"""CLI wrapper for Fujifilm PTP memory operations.

Mitigation (volatile RAM): docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
DRAM is 100 percent volatile; power-cycling clears hung execution (0 percent flash risk).
Firmware repacking: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
Hardware: docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ptp import (
    PTPClient,
    LoopbackTransport,
    FIRM_PTP,
    DRAM_STAGING,
    OP_READ_MEMORY,
    OP_WRITE_MEMORY,
    OP_EXEC_CODE,
    MITIGATION_LINK,
    PTP_MITIGATION,
)

MITIGATION_TEXT = (
    "Failure mitigation: DRAM is 100 percent volatile; pull battery 30s to clear hung "
    "execution (0 percent flash risk). See docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery. "
    "Firmware-level: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery. "
    "Hardware: docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery."
)


def _make_client(args):
    if getattr(args, "loopback", False):
        return PTPClient(LoopbackTransport())
    return PTPClient()


def cmd_info(args):
    print("Fujifilm PTP (ISO 15740) helper")
    print(f"  FIRM_PTP      = 0x{FIRM_PTP:08x}")
    print(f"  DRAM_STAGING  = 0x{DRAM_STAGING:08x}")
    print(f"  ReadMemory    = 0x{OP_READ_MEMORY:04x}")
    print(f"  WriteMemory   = 0x{OP_WRITE_MEMORY:04x}")
    print(f"  ExecCode      = 0x{OP_EXEC_CODE:04x}")
    print(MITIGATION_TEXT)


def cmd_read(args):
    client = _make_client(args)
    addr = int(args.address, 0)
    length = int(args.length, 0)
    data = client.read_memory(addr, length)
    print(data.hex())
    if args.output:
        Path(args.output).write_bytes(data)


def cmd_write(args):
    client = _make_client(args)
    addr = int(args.address, 0)
    data = bytes.fromhex(args.data.replace("0x", "").replace(" ", ""))
    client.write_memory(addr, data)
    print(f"[+] wrote {len(data)} bytes to 0x{addr:08x}")


def cmd_dump(args):
    client = _make_client(args)
    start = int(args.start, 0)
    size = int(args.size, 0)
    out = args.output
    client.dump_ram(out, start_addr=start, size=size)
    print(f"[+] dumped {size} bytes from 0x{start:08x} to {out}")


def main():
    parser = argparse.ArgumentParser(
        description="Fujifilm PTP memory tools (ISO 15740).",
        epilog=MITIGATION_TEXT,
    )
    parser.add_argument("--loopback", action="store_true", help="Use offline loopback transport (testing). " + MITIGATION_TEXT)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="Show PTP constants and mitigation. " + MITIGATION_TEXT)
    p_info.set_defaults(func=cmd_info)

    p_read = sub.add_parser("read", help="Read memory via PTP. " + MITIGATION_TEXT)
    p_read.add_argument("address")
    p_read.add_argument("length")
    p_read.add_argument("-o", "--output", default=None)
    p_read.set_defaults(func=cmd_read)

    p_write = sub.add_parser("write", help="Write memory via PTP. " + MITIGATION_TEXT)
    p_write.add_argument("address")
    p_write.add_argument("data", help="hex bytes")
    p_write.set_defaults(func=cmd_write)

    p_dump = sub.add_parser("dump", help="Dump RAM via PTP. " + MITIGATION_TEXT)
    p_dump.add_argument("output")
    p_dump.add_argument("--start", default=hex(DRAM_STAGING))
    p_dump.add_argument("--size", default="0x4000")
    p_dump.set_defaults(func=cmd_dump)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"[-] {e}")
        print(MITIGATION_TEXT)
        sys.exit(1)


if __name__ == "__main__":
    main()
