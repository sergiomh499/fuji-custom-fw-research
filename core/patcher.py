"""ARM branch patching helpers."""

import struct
from typing import Union


def encode_arm_branch(from_addr: int, to_addr: int, link: bool = False) -> bytes:
    offset = (to_addr - from_addr - 8) >> 2
    base_opcode = 0xEB000000 if link else 0xEA000000
    return struct.pack("<I", base_opcode | (offset & 0x00FFFFFF))


def inject_payload(
    target_binary: Union[bytearray, bytes], payload_bytes: bytes, hook_addr: int, payload_addr: int
) -> bytearray:
    data = bytearray(target_binary)
    needed = max(len(data), hook_addr + 4, payload_addr + len(payload_bytes))
    if needed > len(data):
        data.extend(b"\x00" * (needed - len(data)))

    data[hook_addr : hook_addr + 4] = encode_arm_branch(hook_addr, payload_addr)
    data[payload_addr : payload_addr + len(payload_bytes)] = payload_bytes
    return data
