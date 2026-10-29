"""Unified CLI entrypoint for the Fujifilm firmware research tools."""

import argparse
import json
import re
import struct
import sys
import urllib.request
from pathlib import Path

try:
    from core.container import FujiContainer, OS_CODE_SIZES
    from core.checksum import calculate_delta
    from core.patcher import encode_arm_branch, inject_payload
    from models.registry import ALL_MODELS, get_model_by_id
except Exception:  # pragma: no cover - fallback for direct execution
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core.container import FujiContainer, OS_CODE_SIZES
    from core.checksum import calculate_delta
    from core.patcher import encode_arm_branch, inject_payload
    from models.registry import ALL_MODELS, get_model_by_id


def _parse_addr(value):
    try:
        return int(value, 0)
    except (ValueError, TypeError):
        return int(value, 16)


def cmd_download(args):
    model = get_model_by_id(args.target)
    if model is None:
        print(f"[-] Unknown model target: {args.target}")
        print("    Available targets: " + ", ".join(m.id for m in ALL_MODELS))
        sys.exit(1)
    out_file = Path(args.output) if args.output else Path(model.fw_filename)
    print(f"[*] Downloading official firmware for {model.name} (v{model.latest_fw})...")
    print(f"    URL: {model.dl_url}")
    print(f"    Target: {out_file}")

    def _progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100.0, downloaded * 100.0 / total_size)
            mb = downloaded / (1024 * 1024)
            tot_mb = total_size / (1024 * 1024)
            sys.stdout.write(f"\r    [{pct:5.1f}%] {mb:5.1f} MB / {tot_mb:5.1f} MB")
            sys.stdout.flush()

    urllib.request.urlretrieve(model.dl_url, out_file, reporthook=_progress)
    print(f"\n[+] Download complete: {out_file}")


def cmd_info(args):
    data = Path(args.dat_file).read_bytes()
    fw = FujiContainer(data)
    meta = fw.to_metadata()
    print("=" * 48)
    print(" Fujifilm Firmware Header Info")
    print("=" * 48)
    print(f" File:         {args.dat_file}")
    print(f" OS / Type:    {meta['os_type']}")
    print(f" Model Code:   {meta['model_code']}")
    model = None
    try:
        from models.registry import resolve_model_from_code
        model = resolve_model_from_code(meta["model_code"])
    except Exception:
        model = None
    if model is not None:
        print(f" Identified:   {model.name} ({model.processor})")
        print(f" Sensor:       {model.sensor}")
    print(f" Version:      {meta['version']} (v1={hex(meta['version1'])}, v2={hex(meta['version2'])})")
    print(f" Checksum:     0x{meta['checksum']:08x}")
    print(f" Header Size:  {meta['header_size']} bytes")
    print(f" Payload Size: {meta['payload_size']} bytes ({meta['payload_size'] / (1024*1024):.2f} MB)")
    print("=" * 48)


def cmd_unpack(args):
    src = Path(args.dat_file)
    dst_bin = Path(args.output_bin)
    dst_meta = dst_bin.with_suffix(".json")

    data = src.read_bytes()
    fw = FujiContainer(data)
    unpacked = fw.get_unpacked_payload()

    dst_bin.write_bytes(unpacked)
    meta = fw.to_metadata()
    dst_meta.write_text(json.dumps(meta, indent=2))
    print(f"[+] Written raw ARM binary: {dst_bin}")
    print(f"[+] Written metadata file:  {dst_meta}")


def cmd_repack(args):
    bin_path = Path(args.input_bin)
    meta_path = Path(args.meta_json)
    out_path = Path(args.output_dat)

    meta = json.loads(meta_path.read_text())
    modified_payload = bin_path.read_bytes()

    custom_version = args.version
    out_dat = FujiContainer.repack(
        modified_payload,
        meta,
        increment_version=args.increment_version,
        custom_version=custom_version,
    )
    out_path.write_bytes(out_dat)
    print(f"[+] Repacked firmware written to: {out_path}")


def cmd_scan(args):
    bin_path = Path(args.bin_file)
    data = bin_path.read_bytes()
    keywords = [k.strip().lower() for k in args.filter.split(",")] if args.filter else []
    matches = []
    for match in re.finditer(rb"[a-zA-Z0-9_./ -]{4,}", data):
        text = match.group(0).decode("latin1")
        if not keywords or any(k in text.lower() for k in keywords):
            matches.append((match.start(), text))
    print(f"[+] Found {len(matches)} string matches (showing first {min(args.limit, len(matches))}):")
    for offset, text in matches[: args.limit]:
        print(f"  0x{offset:08x}: {text}")


def cmd_patch_branch(args):
    from_addr = _parse_addr(args.from_addr)
    to_addr = _parse_addr(args.to_addr)
    instr = encode_arm_branch(from_addr, to_addr, link=args.link)
    opcode = struct.unpack("<I", instr)[0]
    print(f"{opcode:08x}")


def cmd_patch_inject(args):
    input_path = Path(args.input_bin)
    payload_path = Path(args.payload_bin)
    hook_addr = _parse_addr(args.hook_addr)
    payload_addr = _parse_addr(args.payload_addr)
    output_path = Path(args.output_bin)

    data = input_path.read_bytes()
    payload = payload_path.read_bytes()
    out = inject_payload(data, payload, hook_addr, payload_addr)
    output_path.write_bytes(out)
    print(f"[+] Injected payload ({len(payload)} bytes) at 0x{payload_addr:08x}")
    print(f"[+] Branch at 0x{hook_addr:08x} -> 0x{payload_addr:08x}")
    print(f"[+] Wrote {output_path}")
def cmd_patch_wifi(args):
    """Apply defensive Wi-Fi stack patch; mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery"""
    from core.wifi_patch import apply_defensive_patch
    from core.container import FujiContainer

    input_path = Path(args.input)
    output_path = Path(args.output)
    data = input_path.read_bytes()

    is_dat = False
    fw = None
    try:
        fw = FujiContainer(data)
        is_dat = True
    except Exception:
        is_dat = False

    if is_dat:
        payload = fw.get_unpacked_payload()
        patched_payload = apply_defensive_patch(payload)
        meta = fw.to_metadata()
        out = FujiContainer.repack(
            patched_payload, meta, increment_version=args.increment_version
        )
        output_path.write_bytes(out)
        print(f"[+] Patched Wi-Fi stack in firmware .DAT")
        print(f"[+] Wrote {output_path}")
    else:
        patched = apply_defensive_patch(data)
        output_path.write_bytes(patched)
        print(f"[+] Patched Wi-Fi stack in binary")
        print(f"[+] Wrote {output_path}")



def cmd_analyze_x10(args):
    """Analyze an X-T10 firmware binary (.bin or .DAT).

    Failure mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
    """
    bin_path = Path(args.bin_file)
    if not bin_path.exists():
        print(f"[-] Binary not found: {bin_path}")
        return
    raw = bin_path.read_bytes()

    # Accept either an unpacked .bin or a packed .DAT (auto-unpack).
    try:
        from core.container import FujiContainer

        fw = FujiContainer(raw)
        data = bytes(fw.get_unpacked_payload())
        print(f"[*] Detected .DAT container; unpacked {len(data):,} bytes")
    except Exception:
        data = raw

    print("=" * 60)
    print(" Fujifilm X10 Firmware Analysis (v2.01)")
    print(f" Loaded: {len(data):,} bytes")
    print("=" * 60)

    try:
        from core.x10_analyzer import X10Analyzer
    except Exception as exc:
        print(f"[-] X10Analyzer unavailable: {exc}")
        return

    analyzer = X10Analyzer(data)
    res = analyzer.analyze()

    hdr = res.get("header")
    if hdr:
        print("\n[1] Header:")
        for k in ("os_type", "model_code", "version", "checksum", "header_size", "payload_size"):
            print(f"    {k}: {hdr.get(k)}")

    vecs = res.get("vectors") or []
    print(f"\n[2] ARMv5TE vector table ({len(vecs)} words):")
    for idx, w in enumerate(vecs):
        print(f"    V{idx}: 0x{w:08x}")

    vt = res.get("vector_tables") or []
    print(f"    vector-table candidates: {len(vt)}")

    p = res.get("printim") or {}
    print("\n[3] PRINTIM hook:")
    print(f"    string offsets: {p.get('string_offsets')}")
    print(f"    entry point:    0x{p.get('entry_point', 0):08x}")
    print(f"    entry refs:     {len(p.get('entry_refs', []))}")

    lb = res.get("lens_barrel") or {}
    print("\n[4] Lens-barrel rotary-switch power-on:")
    print(f"    markers: {len(lb.get('marker_offsets', []))} @ {lb.get('marker_offsets', [])[:8]}")

    cms = res.get("color_matrices") or []
    print(f"\n[5] 2/3\" sensor color matrices: {len(cms)}")
    for c in cms[:5]:
        print(f"    0x{c['offset']:08x}: {c.get('values')}")

    print("\n[+] Analysis complete.")
    print("    Failure mitigation: " + "docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery")


def cmd_analyze_xt20(args):
    bin_path = Path(args.bin_file)
    if not bin_path.exists():
        print(f"[-] Input file not found: {bin_path}")
        return
    raw = bin_path.read_bytes()
    try:
        from core.container import FujiContainer
        fw = FujiContainer(raw)
        data = bytes(fw.get_unpacked_payload())
        print(f"[*] Detected .DAT container; unpacked {len(data):,} bytes")
    except Exception:
        data = raw
    print("=" * 60)
    print(" Fujifilm X-T20 Firmware Analysis (X-Trans III / v2.11)")
    print(f" Loaded: {len(data):,} bytes")
    print("=" * 60)
    from core.xt20_extractor import XT20Extractor
    extractor = XT20Extractor(data)
    res = extractor.analyze()
    acros_list = res.get("acros", [])
    print(f"[+] ACROS Descriptors: {len(acros_list)}")
    for desc in acros_list[:5]:
        print(f"    - {desc.get('name')} @ 0x{desc.get('offset', 0):08x} (matrix @ 0x{desc.get('matrix_offset', 0):08x})")
    wifi = res.get("wifi", {})
    print(f"[+] Wi-Fi KASAGO Markers: {len(wifi.get('markers', {}))}")
    print("[+] Analysis complete.")


def cmd_analyze_xt30(args):
    bin_path = Path(args.bin_file)
    if not bin_path.exists():
        print(f"[-] Input file not found: {bin_path}")
        return
    raw = bin_path.read_bytes()
    try:
        from core.container import FujiContainer
        fw = FujiContainer(raw)
        data = bytes(fw.get_unpacked_payload())
        print(f"[*] Detected .DAT container; unpacked {len(data):,} bytes")
    except Exception:
        data = raw
    print("=" * 60)
    print(" Fujifilm X-T30 Firmware Analysis (X-Trans IV / v2.01)")
    print(f" Loaded: {len(data):,} bytes")
    print("=" * 60)
    from core.xt30_extractor import XT30Extractor
    extractor = XT30Extractor(data)
    res = extractor.analyze()
    print(f"[+] Film Tokens Found: {len(res.get('film_tokens', []))}")
    print(f"[+] Classic Negative Hits: {len(res.get('classic_negative', []))}")
    print(f"[+] Color Chrome Markers: {len(res.get('color_chrome', []))}")
    print(f"[+] Extracted 3x3 Matrices: {len(res.get('matrices', []))}")
    print("[+] Analysis complete.")


def build_parser():
    parser = argparse.ArgumentParser(description="Fujifilm Camera Firmware Tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_download = sub.add_parser("download", help="Download official firmware")
    p_download.add_argument("target", help="Camera model ID")
    p_download.add_argument("-o", "--output", help="Optional output filename")
    p_download.set_defaults(func=cmd_download)

    p_info = sub.add_parser("info", help="Inspect .DAT firmware header")
    p_info.add_argument("dat_file", help="Path to FWUPxxxx.DAT")
    p_info.set_defaults(func=cmd_info)

    p_unpack = sub.add_parser("unpack", help="Unpack and decrypt .DAT to raw ARM binary")
    p_unpack.add_argument("dat_file", help="Path to FWUPxxxx.DAT")
    p_unpack.add_argument("output_bin", help="Path to output decrypted binary")
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

    p_patch = sub.add_parser("patch", help="Binary patch helpers")
    patch_sub = p_patch.add_subparsers(dest="patch_cmd", required=True)
    p_branch = patch_sub.add_parser("branch", help="Print 4-byte ARM32 branch instruction")
    p_branch.add_argument("from_addr")
    p_branch.add_argument("to_addr")
    p_branch.add_argument("--link", action="store_true", help="Use bl instead of b")
    p_branch.set_defaults(func=cmd_patch_branch)

    p_inject = patch_sub.add_parser("inject", help="Inject payload and write output binary")
    p_inject.add_argument("input_bin")
    p_inject.add_argument("payload_bin")
    p_inject.add_argument("hook_addr")
    p_inject.add_argument("payload_addr")
    p_inject.add_argument("output_bin")
    p_inject.set_defaults(func=cmd_patch_inject)

    p_wifi = patch_sub.add_parser(
        "wifi",
        help="Apply defensive Wi-Fi stack patch (KASAGO)",
        epilog="Failure mitigation: if patching fails, restore via docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery (DISP/BACK forced update & version increment).",
    )
    p_wifi.add_argument("input", help="Path to DAT or unpacked .bin")
    p_wifi.add_argument("output", help="Path to write patched file")
    p_wifi.add_argument("--increment-version", action="store_true", help="Increment version if patching a .DAT")
    p_wifi.set_defaults(func=cmd_patch_wifi)


    p_analyze = sub.add_parser("analyze", help="Model-specific analysis")
    analyze_sub = p_analyze.add_subparsers(dest="analyze_cmd", required=True)
    p_xt10 = analyze_sub.add_parser("xt10", help="Analyze X-T10 binary")
    p_xt10.add_argument("bin_file", nargs="?", default="xt10_v131.bin")
    p_xt10.set_defaults(func=cmd_analyze_x10)

    p_x10 = analyze_sub.add_parser(
        "x10",
        help="Analyze FinePix X10 firmware (v2.01)",
        epilog="Failure mitigation: if analysis/patching fails, recover via docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery (DISP/BACK forced update). Volatile RAM: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery. Hard brick: docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery.",
    )
    p_x10.add_argument("bin_file", nargs="?", default="x10_v201.bin", help="Path to unpacked .bin or .DAT")
    p_x10.set_defaults(func=cmd_analyze_x10)

    p_xt20 = analyze_sub.add_parser(
        "xt20",
        help="Analyze Fujifilm X-T20 firmware (v2.11)",
        epilog="Failure mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery",
    )
    p_xt20.add_argument("bin_file", nargs="?", default="xt20_v211.bin", help="Path to unpacked .bin or .DAT")
    p_xt20.set_defaults(func=cmd_analyze_xt20)

    p_xt30 = analyze_sub.add_parser(
        "xt30",
        help="Analyze Fujifilm X-T30 firmware (v2.01)",
        epilog="Failure mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery",
    )
    p_xt30.add_argument("bin_file", nargs="?", default="xt30_v201.bin", help="Path to unpacked .bin or .DAT")
    p_xt30.set_defaults(func=cmd_analyze_xt30)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
