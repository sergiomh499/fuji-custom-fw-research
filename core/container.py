"""Fujifilm firmware container parsing and repacking."""

import struct
from typing import Any

OS_CODE_SIZES = {1: 64, 2: 128, 3: 512, 4: 512, 5: 512, 6: 512, 8: 512}


class FujiContainer:
    def __init__(self, raw_bytes: bytes):
        self.raw = bytearray(raw_bytes)
        self.os_type = struct.unpack("<I", self.raw[0:4])[0]
        if self.os_type not in OS_CODE_SIZES:
            raise ValueError(f"Unsupported firmware OS/type: {self.os_type}")

        self.code_size = OS_CODE_SIZES[self.os_type]
        self.header_size = self.code_size + 20

        raw_code = self.raw[4 : 4 + self.code_size]
        self.model_code = "".join(
            chr(raw_code[i]) for i in range(1, len(raw_code), 2) if raw_code[i] != 0
        ).strip("\x00")

        offset = 4 + self.code_size
        self.v1, self.v2, self.checksum, self.end = struct.unpack(
            "<IIII", self.raw[offset : offset + 16]
        )

        self.payload_raw = bytes(self.raw[self.header_size :])

    @property
    def version_str(self) -> str:
        return f"{self.v1:x}.{self.v2:02x}" if self.v2 < 100 else f"{self.v1:x}.{self.v2:x}"

    def get_unpacked_payload(self) -> bytearray:
        return bytearray((~b) & 0xFF for b in self.payload_raw)

    def to_metadata(self) -> dict:
        unpacked = self.get_unpacked_payload()
        return {
            "os_type": self.os_type,
            "code_size": self.code_size,
            "header_size": self.header_size,
            "model_code": self.model_code,
            "v1": self.v1,
            "v2": self.v2,
            "version1": self.v1,
            "version2": self.v2,
            "version_str": self.version_str,
            "version": self.version_str,
            "checksum": self.checksum,
            "checksum_int": self.checksum,
            "checksum_hex": f"0x{self.checksum:08x}",
            "end": self.end,
            "payload_size": len(self.payload_raw),
            "orig_payload_sum": sum(unpacked),
            "raw_header_hex": self.raw[: self.header_size].hex(),
        }

    @classmethod
    def repack(
        cls,
        modified_payload: bytes,
        metadata: dict,
        increment_version: bool = False,
        custom_version: str = None,
    ) -> bytes:
        os_type = metadata["os_type"]
        code_size = metadata.get("code_size", OS_CODE_SIZES[os_type])
        header_size = metadata.get("header_size", code_size + 20)

        if "raw_header_hex" in metadata and metadata["raw_header_hex"]:
            header = bytearray.fromhex(metadata["raw_header_hex"])
        else:
            header = bytearray(header_size)
            struct.pack_into("<I", header, 0, os_type)
            model_code = metadata.get("model_code", "")
            for i, ch in enumerate(model_code):
                idx = 4 + 1 + i * 2
                if idx < 4 + code_size:
                    header[idx] = ord(ch)
            off = 4 + code_size
            v1 = metadata.get("version1", metadata.get("v1", 1))
            v2 = metadata.get("version2", metadata.get("v2", 0))
            end = metadata.get("end", 0)
            struct.pack_into("<IIII", header, off, v1, v2, 0, end)

        off = 4 + code_size
        v1, v2, _old_checksum, end = struct.unpack("<IIII", header[off : off + 16])

        if custom_version:
            parts = custom_version.split(".")
            v1 = int(parts[0], 16) if len(parts) > 0 and parts[0] else v1
            if len(parts) > 1 and parts[1]:
                v2 = int(parts[1], 16)
        elif increment_version:
            v2 += 1

        orig_sum = metadata.get("orig_payload_sum")
        orig_checksum = metadata.get("checksum_int", metadata.get("checksum", _old_checksum))
        try:
            orig_checksum = int(orig_checksum)
        except (TypeError, ValueError):
            orig_checksum = _old_checksum

        new_sum = sum(modified_payload)
        if orig_sum is not None:
            new_checksum = (orig_checksum - (new_sum - int(orig_sum))) & 0xFFFFFFFF
        else:
            new_checksum = orig_checksum

        struct.pack_into("<IIII", header, off, v1, v2, new_checksum, end)

        inverted = bytes((~b) & 0xFF for b in modified_payload)
        return bytes(header) + inverted
