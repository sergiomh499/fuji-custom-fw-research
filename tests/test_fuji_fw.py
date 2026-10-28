"""
Unit and round-trip smoke test for fuji_fw.py
"""

import struct
import tempfile
from pathlib import Path
import subprocess
import sys

def test_roundtrip():
    # Construct a synthetic Type 4 header
    os_type = 4
    code_size = 512
    # Interleaved model code: '0', '0', '0', '5', '1'
    code_chars = "00051"
    code_bytes = bytearray(512)
    for i, c in enumerate(code_chars):
        code_bytes[1 + i*2] = ord(c)
        code_bytes[i*2] = ord('3')

    v1 = 1
    v2 = 0x31
    orig_payload = b"TESTING_ARM32_CODE_PAYLOAD_HERE_123456789"
    # Inverted for DAT storage
    stored_payload = bytes((~b) & 0xFF for b in orig_payload)

    # Calculate checksum:
    # checksum = (0x100000000 - sum(orig_payload)) & 0xFFFFFFFF
    # Let's verify sum delta logic
    checksum = 0x12345678
    end = 0

    header = struct.pack("<I", os_type) + bytes(code_bytes) + struct.pack("<IIII", v1, v2, checksum, end)
    synthetic_dat = header + stored_payload

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        dat_path = tmp / "FWUP0007.DAT"
        bin_path = tmp / "unpacked.bin"
        repacked_dat = tmp / "REPACKED.DAT"

        dat_path.write_bytes(synthetic_dat)

        # 1. Test unpack
        res = subprocess.run(
            [sys.executable, "tools/fuji_fw.py", "unpack", str(dat_path), str(bin_path)],
            capture_output=True,
            text=True,
            check=True
        )
        assert bin_path.exists()
        unpacked_data = bin_path.read_bytes()
        assert unpacked_data == orig_payload, f"Expected {orig_payload}, got {unpacked_data}"
        print("[PASS] Unpack correctly inverted bits back to original payload")

        # 2. Test info
        res = subprocess.run(
            [sys.executable, "tools/fuji_fw.py", "info", str(dat_path)],
            capture_output=True,
            text=True,
            check=True
        )
        assert "Model Code:   00051" in res.stdout
        assert "Version:      1.31" in res.stdout
        print("[PASS] Header info parsed accurately")

        # 3. Modify one byte and repack with increment version
        mod_data = bytearray(unpacked_data)
        mod_data[0] = ord('X')  # Change 'T' (0x54=84) to 'X' (0x58=88) -> sum increases by 4
        bin_path.write_bytes(mod_data)

        meta_json = tmp / "unpacked.json"
        res = subprocess.run(
            [sys.executable, "tools/fuji_fw.py", "repack", str(bin_path), str(meta_json), str(repacked_dat), "--increment-version"],
            capture_output=True,
            text=True,
            check=True
        )
        assert repacked_dat.exists()

        # Check repacked header
        repacked_bytes = repacked_dat.read_bytes()
        rep_v1, rep_v2, rep_cksum = struct.unpack("<III", repacked_bytes[516:528])
        assert rep_v2 == 0x32, f"Expected v2 increment to 0x32, got {hex(rep_v2)}"
        expected_cksum = (checksum - 4) & 0xFFFFFFFF
        assert rep_cksum == expected_cksum, f"Expected checksum {hex(expected_cksum)}, got {hex(rep_cksum)}"
        print("[PASS] Repack accurately adjusted checksum and version")

        # 4. Unpack repacked file to ensure round-trip integrity
        bin2_path = tmp / "unpacked2.bin"
        subprocess.run(
            [sys.executable, "tools/fuji_fw.py", "unpack", str(repacked_dat), str(bin2_path)],
            check=True
        )
        assert bin2_path.read_bytes() == bytes(mod_data)
        print("[PASS] Round-trip payload matches modified input perfectly")


def test_x10_model_identification():
    os_type = 4
    code_bytes = bytearray(512)
    code_chars = "00010221"
    for i, c in enumerate(code_chars):
        code_bytes[1 + i*2] = ord(c)
        code_bytes[i*2] = ord('3')

    v1 = 2
    v2 = 0x01
    checksum = 0x38261731
    end = 1
    payload = bytes((~b) & 0xFF for b in b"X10_EXR_FIRMWARE_PAYLOAD")

    header = struct.pack("<I", os_type) + bytes(code_bytes) + struct.pack("<IIII", v1, v2, checksum, end)
    synthetic_dat = header + payload

    with tempfile.TemporaryDirectory() as tmpdir:
        dat_path = Path(tmpdir) / "FPUPDATE.DAT"
        dat_path.write_bytes(synthetic_dat)

        res = subprocess.run(
            [sys.executable, "tools/fuji_fw.py", "info", str(dat_path)],
            capture_output=True,
            text=True,
            check=True
        )
        assert "Fujifilm X10" in res.stdout, res.stdout
        assert "EXR Processor (1st Gen)" in res.stdout, res.stdout
        assert "Version:      2.01" in res.stdout, res.stdout
        print("[PASS] Fujifilm X10 identified accurately from header")

if __name__ == "__main__":
    test_roundtrip()
    test_x10_model_identification()
