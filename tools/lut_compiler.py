#!/usr/bin/env python3
"""Compile .cube LUTs to Fujifilm DSP matrices (Q15) or patch firmware.

Failure mitigations:
  Firmware repacking/patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
  Volatile/PTP memory: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
  Hardware flashing: docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lut_compiler import (
    CubeLUTParser,
    DSPMatrixOptimizer,
    ToneCurveExtractor,
    PRESETS_FULL,
    get_preset,
    list_presets,
    MITIGATION_FIRMWARE,
)
from core.film_simulation import FilmSimulationPatcher
from core.container import FujiContainer

MITIGATION_TEXT = (
    "Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery "
    "(fall back to identity matrix on numerical instability). "
    "PTP: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery. "
    "Hardware: docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery."
)


def cmd_compile(args):
    if args.preset:
        p = get_preset(args.preset)
        result = {
            "preset": args.preset,
            "matrix_float": p["matrix_float"],
            "matrix_q15": p["matrix"],
            "tone_curve": p["tone_curve"],
            "mitigation": MITIGATION_FIRMWARE,
        }
    else:
        parser = CubeLUTParser(args.input)
        opt = DSPMatrixOptimizer(parser)
        curve = ToneCurveExtractor(parser).extract(parser)
        result = {
            "title": parser.title,
            "size": parser.size,
            "matrix_float": opt.matrix_float,
            "matrix_q15": opt.matrix_q15,
            "tone_curve": curve,
            "mitigation": MITIGATION_FIRMWARE,
        }
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text)
        print(f"[+] Wrote {args.output}")
    else:
        print(text)


def cmd_patch(args):
    inp = Path(args.input) if args.input else None
    if args.preset:
        p = get_preset(args.preset)
        matrix = p["matrix"]
        curve = p["tone_curve"]
    else:
        if inp is None:
            print("[-] --input cube or --preset required")
            sys.exit(1)
        parser = CubeLUTParser(inp)
        opt = DSPMatrixOptimizer(parser)
        matrix = opt.matrix_q15
        curve = ToneCurveExtractor(parser).extract(parser)
    data = Path(args.firmware).read_bytes()
    token = args.token
    try:
        fw = FujiContainer(data)
        is_dat = True
    except Exception:
        fw = None
        is_dat = False
    if is_dat:
        payload = bytearray(fw.get_unpacked_payload())
        patcher = FilmSimulationPatcher(payload)
        patcher.set_matrix(token, matrix)
        try:
            patcher.inject_lut(token, curve)
        except Exception:
            pass
        patched_payload = patcher.generate()
        meta = fw.to_metadata()
        out = FujiContainer.repack(patched_payload, meta, increment_version=args.increment_version)
        Path(args.output).write_bytes(out)
    else:
        patcher = FilmSimulationPatcher(data)
        patcher.set_matrix(token, matrix)
        try:
            patcher.inject_lut(token, curve)
        except Exception:
            pass
        Path(args.output).write_bytes(patcher.generate())
    print(f"[+] Patched {token} -> {args.output}")
    print(f"    mitigation: {MITIGATION_FIRMWARE}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Compile .cube 3D-LUTs to Fujifilm DSP color matrices (Q15). " + MITIGATION_TEXT,
        epilog=MITIGATION_TEXT,
    )
    sub = parser.add_subparsers(dest="command")

    # top-level compile convenience
    parser.add_argument("input", nargs="?", help="Input .cube file")
    parser.add_argument("-o", "--output", help="Output JSON/bin path")
    parser.add_argument("--preset", choices=list_presets(), help="Use built-in preset")
    parser.add_argument("--firmware", help="Firmware binary to patch (patch mode)")
    parser.add_argument("--token", default="PROV", help="Film simulation token")
    parser.add_argument("--increment-version", action="store_true", help="Increment firmware version")

    p_compile = sub.add_parser("compile", help="Compile .cube to JSON. " + MITIGATION_TEXT)
    p_compile.add_argument("input", nargs="?")
    p_compile.add_argument("-o", "--output")
    p_compile.add_argument("--preset", choices=list_presets())

    p_patch = sub.add_parser("patch", help="Patch firmware with LUT matrix. " + MITIGATION_TEXT)
    p_patch.add_argument("--firmware", required=True)
    p_patch.add_argument("--input")
    p_patch.add_argument("--preset", choices=list_presets())
    p_patch.add_argument("--token", default="PROV")
    p_patch.add_argument("-o", "--output", required=True)
    p_patch.add_argument("--increment-version", action="store_true")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    # dispatch
    if args.command == "patch":
        cmd_patch(args)
        return
    if args.command == "compile":
        # normalize
        if not hasattr(args, "preset"):
            args.preset = None
        if not hasattr(args, "output"):
            args.output = None
        cmd_compile(args)
        return
    # top-level: if firmware provided -> patch
    if getattr(args, "firmware", None):
        # map
        ns = argparse.Namespace(
            firmware=args.firmware,
            input=args.input,
            preset=args.preset,
            token=getattr(args, "token", "PROV"),
            output=args.output,
            increment_version=getattr(args, "increment_version", False),
        )
        cmd_patch(ns)
    else:
        cmd_compile(args)


if __name__ == "__main__":
    main()
