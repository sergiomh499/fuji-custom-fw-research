import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.checksum import calculate_delta
from core.container import FujiContainer, OS_CODE_SIZES
from core.patcher import encode_arm_branch, inject_payload
from core.structures import OSDMenuTable, FilmSimulationRegistry, SQLiteSchemaParser
from models.registry import ALL_MODELS, get_model_by_id, resolve_model_from_code


def _make_synthetic_dat():
    os_type = 4
    code_size = 512
    code_bytes = bytearray(512)
    code_chars = "00051"
    for i, c in enumerate(code_chars):
        code_bytes[1 + i * 2] = ord(c)
        code_bytes[i * 2] = ord("3")
    v1 = 1
    v2 = 0x31
    orig_payload = b"TESTING_ARM32_CODE_PAYLOAD_HERE_123456789"
    stored_payload = bytes((~b) & 0xFF for b in orig_payload)
    checksum = 0x12345678
    end = 0
    header = struct.pack("<I", os_type) + bytes(code_bytes) + struct.pack("<IIII", v1, v2, checksum, end)
    return header + stored_payload, orig_payload, checksum


class TestModular(unittest.TestCase):
    def test_checksum(self):
        assert calculate_delta(10, 14, 100) == 96


    def test_container_roundtrip(self):
        synthetic_dat, orig_payload, checksum = _make_synthetic_dat()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dat = tmp / "FWUP0007.DAT"
            binp = tmp / "out.bin"
            meta = tmp / "out.json"
            repacked = tmp / "repacked.DAT"
            dat.write_bytes(synthetic_dat)

            # CLI unpack
            subprocess.run([sys.executable, str(ROOT / "fujitool"), "unpack", str(dat), str(binp)], check=True, cwd=str(ROOT))
            assert binp.read_bytes() == orig_payload

            # modify
            mod = bytearray(orig_payload)
            mod[0] = ord("X")
            binp.write_bytes(mod)

            subprocess.run([sys.executable, str(ROOT / "fujitool"), "repack", str(binp), str(meta if False else binp.with_suffix(".json")), str(repacked), "--increment-version"], check=True, cwd=str(ROOT))
            assert repacked.exists()

            # verify via container
            fw = FujiContainer(repacked.read_bytes())
            assert fw.v2 == 0x32


    def test_patcher(self):
        instr = encode_arm_branch(0x1000, 0x1008)
        assert instr == struct.pack("<I", 0xEA000000)
        out = inject_payload(b"\x00" * 256, b"\xde\xad\xbe\xef", 0x10, 0x80)
        assert out[0x10:0x14] == encode_arm_branch(0x10, 0x80)


    def test_structures(self):
        data = b"CREATE TABLE foo (id INT);" + b"\x00" * 10
        tables = SQLiteSchemaParser.extract_tables(data)
        assert tables and tables[0]["name"] == "foo"
        entries = OSDMenuTable.parse(b"\x00" * 1000, base_offset=0, stride=10)
        assert isinstance(entries, list)
        res = FilmSimulationRegistry.parse_tokens(b"PROV" + b"\x00" * 10, search_range=(0, 100))
        assert isinstance(res, list)


    def test_registry(self):
        assert get_model_by_id("xt10") is not None
        assert get_model_by_id("nope") is None
        m = resolve_model_from_code("00051001000")
        assert m is not None and m.id == "xt10"
        assert len(ALL_MODELS) >= 2


    def test_cli_info(self):
        synthetic_dat, orig_payload, checksum = _make_synthetic_dat()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dat = tmp / "FWUP0007.DAT"
            dat.write_bytes(synthetic_dat)
            res = subprocess.run([sys.executable, str(ROOT / "fujitool"), "info", str(dat)], capture_output=True, text=True, cwd=str(ROOT))
            assert res.returncode == 0
            assert "Model Code:   00051" in res.stdout


    def test_cli_help(self):
        res = subprocess.run([sys.executable, str(ROOT / "fujitool"), "--help"], capture_output=True, text=True, cwd=str(ROOT))
        assert res.returncode == 0
        for cmd in ["download", "info", "unpack", "repack", "scan", "patch", "analyze"]:
            assert cmd in res.stdout


    def test_cli_patch_branch(self):
        res = subprocess.run([sys.executable, str(ROOT / "fujitool"), "patch", "branch", "0x1000", "0x1008"], capture_output=True, text=True, cwd=str(ROOT))
        assert res.returncode == 0
        assert "ea000000" in res.stdout


    def test_cli_analyze_xt10(self):
        # just ensure command runs (missing file handled)
        res = subprocess.run([sys.executable, str(ROOT / "fujitool"), "analyze", "xt10", "nonexistent.bin"], capture_output=True, text=True, cwd=str(ROOT))
        assert res.returncode == 0

    def test_xt20_and_xt30_models(self):
        m20 = get_model_by_id("xt20")
        assert m20 is not None
        assert m20.name == "Fujifilm X-T20"
        assert m20.processor == "X-Processor Pro"

        m30 = get_model_by_id("xt30")
        assert m30 is not None
        assert m30.name == "Fujifilm X-T30"
        assert m30.processor == "X-Processor 4"
