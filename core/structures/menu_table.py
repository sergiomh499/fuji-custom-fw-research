"""Fuji OSD menu table parsing."""


class OSDMenuTable:
    @staticmethod
    def parse(data: bytes, base_offset: int = 0x00805DC0, stride: int = 50) -> list:
        entries = []
        count = 507
        for i in range(count):
            addr = base_offset + i * stride
            if addr + stride > len(data):
                break
            slot = data[addr : addr + stride]
            # Extract first printable ASCII run as the menu name.
            name = ""
            run = bytearray()
            for b in slot:
                if 32 <= b < 127:
                    run.append(b)
                else:
                    if len(run) >= 3:
                        name = run.decode("ascii", errors="replace")
                        break
                    run = bytearray()
            if not name and len(run) >= 3:
                name = run.decode("ascii", errors="replace")
            entries.append((addr, name))
        return entries

    @staticmethod
    def find_menu(entries, name: str):
        for idx, (addr, entry_name) in enumerate(entries):
            if entry_name == name:
                return (idx, addr, entry_name)
        for idx, (addr, entry_name) in enumerate(entries):
            if entry_name.lower() == name.lower():
                return (idx, addr, entry_name)
        for idx, (addr, entry_name) in enumerate(entries):
            if name.lower() in entry_name.lower():
                return (idx, addr, entry_name)
        return None
