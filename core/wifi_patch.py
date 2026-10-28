"""Defensive Wi-Fi stack patch helpers for Fujifilm X-T10 firmware."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable, Mapping, Sequence

ARM_NOP = b"\x00\xf0\x20\xe3"  # ARMv7 NOP
ARM_BX_LR = b"\x1e\xff\x2f\xe1"  # bx lr


WIFI_STACK_MARKERS: dict[str, bytes] = {
    "kasago_lan_init": b"lanInit",
    "kasago_tcpip_init": b"efTcpIpInit",
    "dhcpd_start": b"tfDhcpdStart",
    "recv_memory_depletion": b"recv Memory Depletiion Err.",
    "stm_ap_soc_halt": b"STM AP_SOC Halt.",
    "http_import_guest": b"IMPORT /guest",
    "discovery": b"DISCOVER",
    "udp_port_51541": b"51541",
    "udp_port_51542": b"51542",
}

MARKER_REGIONS: dict[str, tuple[int, int]] = {
    "network_init": (0x00B4D400, 0x00B4F000),
    "discovery_listener": (0x00B93180, 0x00B93300),
}


@dataclass(frozen=True)
class WifiCrashSite:
    name: str
    offset: int
    marker: bytes
    region: str = ""


@dataclass
class WifiPatchOperation:
    offset: int
    old: bytes
    new: bytes
    reason: str

    def apply(self, data: bytearray) -> None:
        end = self.offset + len(self.old)
        if end > len(data) or data[self.offset:end] != self.old:
            raise ValueError(
                f"patch precondition failed at 0x{self.offset:08x}: "
                f"expected {self.old.hex()}, found {bytes(data[self.offset:end]).hex()}"
            )
        data[self.offset:end] = self.new


@dataclass
class WifiDetectionReport:
    markers: dict[str, list[int]] = field(default_factory=dict)
    sites: list[WifiCrashSite] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def vulnerable(self) -> bool:
        return bool(self.sites) and not self.missing


def find_markers(
    data: bytes | bytearray, markers: Mapping[str, bytes] | None = None
) -> dict[str, list[int]]:
    marker_map = WIFI_STACK_MARKERS if markers is None else markers
    result: dict[str, list[int]] = {}
    for name, needle in marker_map.items():
        offsets: list[int] = []
        start = 0
        while True:
            pos = data.find(needle, start)
            if pos < 0:
                break
            offsets.append(pos)
            start = pos + max(1, len(needle))
        result[name] = offsets
    return result


def _region_name(offset: int) -> str:
    for name, (start, end) in MARKER_REGIONS.items():
        if start <= offset < end:
            return name
    return ""


def identify_wifi_crash_sites(
    data: bytes | bytearray, markers: Mapping[str, bytes] | None = None
) -> list[WifiCrashSite]:
    marker_map = WIFI_STACK_MARKERS if markers is None else markers
    found = find_markers(data, marker_map)
    sites: list[WifiCrashSite] = []
    for name, offsets in found.items():
        for offset in offsets:
            sites.append(
                WifiCrashSite(
                    name=name,
                    offset=offset,
                    marker=marker_map[name],
                    region=_region_name(offset),
                )
            )
    sites.sort(key=lambda site: site.offset)
    return sites


def detect_wifi_vulnerability(
    data: bytes | bytearray, required: Sequence[str] | None = None
) -> WifiDetectionReport:
    required_markers = list(required) if required is not None else list(WIFI_STACK_MARKERS)
    markers = find_markers(data)
    sites = identify_wifi_crash_sites(data)
    missing = [name for name in required_markers if not markers.get(name)]
    return WifiDetectionReport(markers=markers, sites=sites, missing=missing)


def nop_at(data: bytes | bytearray, offset: int, size: int = 4) -> bytearray:
    if offset < 0 or offset + size > len(data):
        raise ValueError("patch offset outside binary")
    if size <= 0 or size % 4:
        raise ValueError("NOP size must be a positive multiple of 4")
    out = bytearray(data)
    out[offset : offset + size] = ARM_NOP * (size // 4)
    return out


def clamp_at(
    data: bytes | bytearray,
    offset: int,
    replacement: bytes,
    expected: bytes | None = None,
) -> bytearray:
    if offset < 0 or offset + len(replacement) > len(data):
        raise ValueError("patch offset outside binary")
    if expected is not None and bytes(data[offset : offset + len(replacement)]) != expected:
        raise ValueError("patch precondition failed")
    out = bytearray(data)
    out[offset : offset + len(replacement)] = replacement
    return out


def build_defensive_patch(
    data: bytes | bytearray,
    sites: Iterable[WifiCrashSite] | None = None,
) -> list[WifiPatchOperation]:
    chosen = list(sites) if sites is not None else identify_wifi_crash_sites(data)
    operations: list[WifiPatchOperation] = []
    for site in chosen:
        if site.offset + 4 > len(data):
            continue
        operations.append(
            WifiPatchOperation(
                offset=site.offset,
                old=bytes(data[site.offset : site.offset + 4]),
                new=ARM_NOP,
                reason=f"NOP guard for {site.name}",
            )
        )
    return operations


def apply_defensive_patch(
    data: bytes | bytearray,
    operations: Sequence[WifiPatchOperation] | None = None,
) -> bytearray:
    ops = list(operations) if operations is not None else build_defensive_patch(data)
    out = bytearray(data)
    for operation in ops:
        operation.apply(out)
    return out


def patch_report(data: bytes | bytearray) -> dict:
    report = detect_wifi_vulnerability(data)
    return {
        "vulnerable": report.vulnerable,
        "marker_offsets": report.markers,
        "sites": [asdict(site) for site in report.sites],
        "missing": report.missing,
        "operations": [asdict(op) for op in build_defensive_patch(data)],
    }


def make_nop_patch(offset: int, size: int = 4, reason: str = "NOP vulnerable handler") -> WifiPatchOperation:
    if size <= 0 or size % 4:
        raise ValueError("NOP size must be a positive multiple of 4")
    return WifiPatchOperation(offset=offset, old=b"", new=ARM_NOP * (size // 4), reason=reason)


make_nop_operation = make_nop_patch


class WifiPatch:
    def detect(self, data):
        return detect_wifi_vulnerability(data)

    def build(self, data, sites=None):
        return build_defensive_patch(data, sites)

    def apply(self, data, operations=None):
        return apply_defensive_patch(data, operations)


WifiPatchEngine = WifiPatch

WiFiPatcher = WifiPatch
WifiPatch.apply_patch = WifiPatch.apply


detect_wifi_crash = detect_wifi_vulnerability
find_wifi_vulnerable_handler = identify_wifi_crash_sites
generate_wifi_patch = build_defensive_patch
apply_wifi_patch = apply_defensive_patch
WifiVulnerabilityReport = WifiDetectionReport
