import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.fuji_patch import encode_arm_branch


def test_encode_arm_branch_forward():
    instr = encode_arm_branch(0x1000, 0x1008)
    assert instr == struct.pack("<I", 0xEA000000)


def test_encode_arm_branch_backward():
    instr = encode_arm_branch(0x1008, 0x1000)
    assert instr == struct.pack("<I", 0xEAFFFFFC)


def test_encode_arm_branch_link():
    instr = encode_arm_branch(0x2000, 0x2008, link=True)
    assert instr == struct.pack("<I", 0xEB000000)


def test_inject_synthetic():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        input_bin = tmp / "in.bin"
        payload_bin = tmp / "payload.bin"
        output_bin = tmp / "out.bin"

        input_bin.write_bytes(b"\x00" * 256)
        payload = b"\xde\xad\xbe\xef"
        payload_bin.write_bytes(payload)

        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "fuji_patch.py"), "inject",
             str(input_bin), str(payload_bin), "0x10", "0x80", str(output_bin)],
            check=True, cwd=str(ROOT),
        )

        out = output_bin.read_bytes()
        assert out[0x10:0x14] == encode_arm_branch(0x10, 0x80)
        assert out[0x80:0x84] == payload


def test_help_runs():
    res = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "fuji_patch.py"), "--help"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert res.returncode == 0


if __name__ == "__main__":
    test_encode_arm_branch_forward()
    test_encode_arm_branch_backward()
    test_encode_arm_branch_link()
    test_inject_synthetic()
    test_help_runs()
    print("[PASS] All fuji_patch tests passed.")
