#!/usr/bin/env python3
"""fuji_patch.py - Inject ARM32 payloads into unpacked Fujifilm binaries."""

import argparse
import struct
import sys
from pathlib import Path

# Best-effort integration with fuji_fw checksum helpers.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fuji_fw  # noqa: F401
except Exception:
    fuji_fw = None


def parse_addr(value):
    try:
        return int(value, 0)
    except (ValueError, TypeError):
        return int(value, 16)


def encode_arm_branch(from_addr, to_addr, link=False):
    """Return 4 bytes (little-endian) for an ARM32 b/bl instruction."""
    offset = (to_addr - from_addr - 8) >> 2
    if link:
        opcode = 0xEB000000 | (offset & 0x00FFFFFF)
    else:
        opcode = 0xEA000000 | (offset & 0x00FFFFFF)
    return struct.pack("<I", opcode)


def cmd_branch(args):
    from_addr = parse_addr(args.from_addr)
    to_addr = parse_addr(args.to_addr)
    instr = encode_arm_branch(from_addr, to_addr, link=args.link)
    opcode = struct.unpack("<I", instr)[0]
    print(f"{opcode:08x}")


def cmd_inject(args):
    input_path = Path(args.input_bin)
    payload_path = Path(args.payload_bin)
    hook_addr = parse_addr(args.hook_addr)
    payload_addr = parse_addr(args.payload_addr)
    output_path = Path(args.output_bin)

    data = bytearray(input_path.read_bytes())
    payload = payload_path.read_bytes()

    needed = max(len(data), hook_addr + 4, payload_addr + len(payload))
    if needed > len(data):
        data.extend(b"\x00" * (needed - len(data)))

    data[hook_addr:hook_addr + 4] = encode_arm_branch(hook_addr, payload_addr)
    data[payload_addr:payload_addr + len(payload)] = payload

    output_path.write_bytes(data)
    print(f"[+] Injected payload ({len(payload)} bytes) at 0x{payload_addr:08x}")
    print(f"[+] Branch at 0x{hook_addr:08x} -> 0x{payload_addr:08x}")
    print(f"[+] Wrote {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Inject ARM32 payloads into unpacked Fujifilm binaries")
    sub = parser.add_subparsers(dest="command", required=True)

    p_branch = sub.add_parser("branch", help="Print 4-byte ARM32 branch instruction")
    p_branch.add_argument("from_addr")
    p_branch.add_argument("to_addr")
    p_branch.add_argument("--link", action="store_true", help="Use bl instead of b")
    p_branch.set_defaults(func=cmd_branch)

    p_inject = sub.add_parser("inject", help="Inject payload and write output binary")
    p_inject.add_argument("input_bin")
    p_inject.add_argument("payload_bin")
    p_inject.add_argument("hook_addr")
    p_inject.add_argument("payload_addr")
    p_inject.add_argument("output_bin")
    p_inject.set_defaults(func=cmd_inject)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
