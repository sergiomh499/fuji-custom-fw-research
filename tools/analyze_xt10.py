#!/usr/bin/env python3
"""
analyze_xt10.py - Automated memory mapper and structure extractor for Fujifilm X-T10

Reads the unpacked ARM32 binary (xt10_v131.bin) and dumps:
1. Film Simulation DSP tokens
2. UI State Machine Menu Table (507 entries)
3. Custom recipe slots (C1-C7)
4. Embedded SQLite schemas
"""

import argparse
import re
import struct
from pathlib import Path

def analyze_xt10(bin_path: Path):
    if not bin_path.exists():
        print(f"[-] Binary not found: {bin_path}")
        print("    Run: python3 tools/fuji_fw.py download xt10 && python3 tools/fuji_fw.py unpack FWUP0007.DAT xt10_v131.bin")
        return

    data = bin_path.read_bytes()
    print("=" * 60)
    print(" Fujifilm X-T10 Firmware Analysis (v1.31)")
    print(f" Loaded: {len(data):,} bytes")
    print("=" * 60)

    # 1. Film Simulation DSP Tokens
    print("\n[1] Film Simulation DSP Tokens (0x0024fb10 - 0x0024fb70)")
    print("-" * 60)
    chunk = data[0x0024fb10:0x0024fb80]
    tokens = []
    for m in re.finditer(b"([A-Za-z0-9_]{3,})", chunk):
        addr = 0x0024fb10 + m.start()
        token = m.group(1).decode("latin1")
        tokens.append((addr, token))
    for addr, token in tokens:
        print(f"  0x{addr:08x}: {token}")

    # 2. UI State Machine Menu Table
    print("\n[2] UI State Machine Menu Table (Base: 0x00805dc0, Stride: 50 bytes)")
    print("-" * 60)
    table_start = 0x00805dc0
    entries = []
    curr = table_start
    while curr < len(data):
        raw = data[curr:curr+50]
        name = raw.split(b"\x00")[0].decode("latin1", errors="ignore")
        if any(c.isalnum() for c in name) and len(name) >= 2:
            entries.append((curr, name))
            curr += 0x32
        else:
            break

    print(f"  Total mapped entries: {len(entries)}")
    interesting_menus = ["AFMENU", "FSIMMENU", "CUSTOMMENU", "AEMENU", "ISOMENU", "WBMENU", "SHUTTERTYPEMENU", "FILMBKTSEL"]
    for idx, (addr, name) in enumerate(entries):
        if name in interesting_menus:
            print(f"  Index {idx:3d} (0x{idx:02x}) @ 0x{addr:08x} -> {name}")

    # 3. Custom Recipe Slots (C1 - C7)
    print("\n[3] Custom Recipe Slots (C1 - C7)")
    print("-" * 60)
    for i in range(1, 8):
        name = f"CUSTOM {i}"
        matches = [m.start() for m in re.finditer(re.escape(name.encode("utf-16le")), data)]
        if matches:
            primary = [m for m in matches if m >= 0x1dc0000]
            addr = primary[0] if primary else matches[0]
            print(f"  Slot C{i} ({name}) @ 0x{addr:08x} (matches: {len(matches)})")

    # 4. Embedded SQLite Schemas
    print("\n[4] Embedded SQLite Database Schemas")
    print("-" * 60)
    for m in re.finditer(b"create table [a-zA-Z0-9_]+", data, re.IGNORECASE):
        addr = m.start()
        query = data[addr:addr+120].split(b"\x00")[0].decode("latin1", errors="ignore")
        print(f"  0x{addr:08x}: {query}")

    print("\n" + "=" * 60)
    print("[+] Analysis complete. See docs/XT10_MEMORY_MAP.md for full reference.")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Fujifilm X-T10 firmware binary")
    parser.add_argument("bin_file", nargs="?", default="xt10_v131.bin", help="Path to xt10_v131.bin")
    args = parser.parse_args()
    analyze_xt10(Path(args.bin_file))
