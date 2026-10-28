#!/usr/bin/env python3
"""
fuji_fw.py - Fujifilm Camera Firmware Reverse Engineering CLI Tool

Handles unpacking, inspecting, disassembling preparation, and repacking
of Fujifilm camera firmware (.DAT files).
"""

import argparse
import json
import struct
import sys
from pathlib import Path

# Model code sizes by firmware header OS type
OS_CODE_SIZES = {
    1: 64,
    2: 128,
    3: 512,
    4: 512,
    5: 512,
    6: 512,
    8: 512,
}


class FujiFirmware:
    def __init__(self, dat_bytes: bytes):
        self.raw = bytearray(dat_bytes)
        self.os_type = struct.unpack("<I", self.raw[0:4])[0]
        if self.os_type not in OS_CODE_SIZES:
            raise ValueError(f"Unsupported firmware OS/type: {self.os_type}")

        self.code_size = OS_CODE_SIZES[self.os_type]
        self.header_size = self.code_size + 20

        raw_code = self.raw[4 : 4 + self.code_size]
        # Fujifilm model code: every other byte is interleaved
        self.model_code = "".join(
            chr(raw_code[i]) for i in range(1, len(raw_code), 2) if raw_code[i] != 0
        ).strip("\x00")

        offset = 4 + self.code_size
        self.v1, self.v2, self.checksum, self.end = struct.unpack(
            "<IIII", self.raw[offset : offset + 16]
        )

        self.payload_raw = self.raw[self.header_size :]

    @property
    def version_str(self) -> str:
        return f"{self.v1:x}.{self.v2:02x}" if self.v2 < 100 else f"{self.v1:x}.{self.v2:x}"

    def get_unpacked_payload(self) -> bytearray:
        """Bitwise NOT inversion of the payload (~byte) to get clear ARM binary."""
        return bytearray((~b) & 0xFF for b in self.payload_raw)

    def to_metadata(self) -> dict:
        return {
            "os_type": self.os_type,
            "code_size": self.code_size,
            "header_size": self.header_size,
            "model_code": self.model_code,
            "version1": self.v1,
            "version2": self.v2,
            "version": self.version_str,
            "checksum": f"0x{self.checksum:08x}",
            "checksum_int": self.checksum,
            "end": self.end,
            "payload_size": len(self.payload_raw),
        }


def cmd_info(args):
    data = Path(args.dat_file).read_bytes()
    fw = FujiFirmware(data)
    meta = fw.to_metadata()
    print("=" * 48)
    print(" Fujifilm Firmware Header Info")
    print("=" * 48)
    print(f" File:         {args.dat_file}")
    print(f" OS / Type:    {meta['os_type']}")
    print(f" Model Code:   {meta['model_code']}")
    print(f" Version:      {meta['version']} (v1={hex(meta['version1'])}, v2={hex(meta['version2'])})")
    print(f" Checksum:     {meta['checksum']}")
    print(f" Header Size:  {meta['header_size']} bytes")
    print(f" Payload Size: {meta['payload_size']} bytes ({meta['payload_size'] / (1024*1024):.2f} MB)")
    print("=" * 48)


def cmd_unpack(args):
    src = Path(args.dat_file)
    dst_bin = Path(args.output_bin)
    dst_meta = dst_bin.with_suffix(".json")

    print(f"[*] Reading {src}...")
    data = src.read_bytes()
    fw = FujiFirmware(data)

    print(f"[*] Model: {fw.model_code}, Version: {fw.version_str}, Checksum: 0x{fw.checksum:08x}")
    print(f"[*] Decrypting payload ({len(fw.payload_raw)} bytes) via bitwise NOT...")
    unpacked = fw.get_unpacked_payload()

    dst_bin.write_bytes(unpacked)
    print(f"[+] Written raw ARM binary: {dst_bin}")

    meta = fw.to_metadata()
    # Save the original un-inverted payload byte sum to accurately track deltas on repack
    meta["orig_payload_sum"] = sum(unpacked)
    meta["raw_header_hex"] = fw.raw[: fw.header_size].hex()
    dst_meta.write_text(json.dumps(meta, indent=2))
    print(f"[+] Written metadata file:  {dst_meta}")
    print("[+] Ready for analysis in Ghidra / IDA (Architecture: ARM little-endian, 32-bit)")


def cmd_repack(args):
    bin_path = Path(args.input_bin)
    meta_path = Path(args.meta_json)
    out_path = Path(args.output_dat)

    meta = json.loads(meta_path.read_text())
    header_raw = bytearray.fromhex(meta["raw_header_hex"])
    code_size = meta["code_size"]

    print(f"[*] Reading modified binary: {bin_path}...")
    modified_payload = bytearray(bin_path.read_bytes())

    orig_sum = meta.get("orig_payload_sum")
    new_sum = sum(modified_payload)
    orig_checksum = meta["checksum_int"]

    if orig_sum is not None:
        delta = new_sum - orig_sum
        new_checksum = (orig_checksum - delta) & 0xFFFFFFFF
    else:
        new_checksum = orig_checksum

    # Version adjustment if requested
    v1 = meta["version1"]
    v2 = meta["version2"]
    if args.increment_version:
        v2 += 1
        print(f"[*] Incrementing version to {v1:x}.{v2:02x}")
    elif args.version:
        parts = args.version.split(".")
        v1 = int(parts[0], 16)
        v2 = int(parts[1], 16)
        print(f"[*] Setting custom version to {v1:x}.{v2:02x}")

    # Update header: version1, version2, checksum
    offset = 4 + code_size
    struct.pack_into("<III", header_raw, offset, v1, v2, new_checksum)

    print(f"[*] New checksum: 0x{new_checksum:08x}")
    print(f"[*] Inverting payload bytes (~byte)...")
    inverted_payload = bytearray((~b) & 0xFF for b in modified_payload)

    out_dat = header_raw + inverted_payload
    out_path.write_bytes(out_dat)
    print(f"[+] Repacked firmware written to: {out_path}")
    print(f"[+] Total size: {len(out_dat)} bytes")


def cmd_scan(args):
    import re
    bin_path = Path(args.bin_file)
    print(f"[*] Scanning strings in {bin_path}...")
    data = bin_path.read_bytes()

    keywords = [k.strip().lower() for k in args.filter.split(",")] if args.filter else []
    matches = []

    for match in re.finditer(b"[a-zA-Z0-9_./ -]{4,}", data):
        text = match.group(0).decode("latin1")
        if not keywords or any(k in text.lower() for k in keywords):
            matches.append((match.start(), text))

    print(f"[+] Found {len(matches)} string matches (showing first {min(args.limit, len(matches))}):")
    for offset, text in matches[: args.limit]:
        print(f"  0x{offset:08x}: {text}")


def main():
    parser = argparse.ArgumentParser(description="Fujifilm Camera Firmware Tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="Inspect .DAT firmware header")
    p_info.add_argument("dat_file", help="Path to FWUPxxxx.DAT")
    p_info.set_defaults(func=cmd_info)

    p_unpack = sub.add_parser("unpack", help="Unpack and decrypt .DAT to raw ARM binary")
    p_unpack.add_argument("dat_file", help="Path to FWUPxxxx.DAT")
    p_unpack.add_argument("output_bin", help="Path to output decrypted binary (e.g., xt10.bin)")
    p_unpack.set_defaults(func=cmd_unpack)

    p_repack = sub.add_parser("repack", help="Repack modified binary into flashable .DAT")
    p_repack.add_argument("input_bin", help="Path to modified ARM binary")
    p_repack.add_argument("meta_json", help="Path to metadata JSON from unpack")
    p_repack.add_argument("output_dat", help="Path to output .DAT file")
    p_repack.add_argument("--increment-version", action="store_true", help="Increment version v2 by 1")
    p_repack.add_argument("--version", help="Set explicit version (e.g. 1.32)")
    p_repack.set_defaults(func=cmd_repack)

    p_scan = sub.add_parser("scan", help="Scan unpacked binary for keywords/strings")
    p_scan.add_argument("bin_file", help="Path to unpacked .bin")
    p_scan.add_argument("--filter", default="film,provia,velvia,focus,sqlite,af,menu", help="Comma-separated keyword filter")
    p_scan.add_argument("--limit", type=int, default=50, help="Max strings to display")
    p_scan.set_defaults(func=cmd_scan)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
