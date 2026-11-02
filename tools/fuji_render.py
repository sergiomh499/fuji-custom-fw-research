#!/usr/bin/env python3
"""Standalone Fujifilm pipeline renderer.

Usage:
    python3 tools/fuji_render.py input.ppm output.ppm --recipe C1
    python3 tools/fuji_render.py input.ppm output.ppm --simulation "Classic Negative" --grain strong --clarity 2

Failure mitigation:
- Volatile / PTP RAM recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
- Firmware repacking / patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline_runner import PipelineRunner
from core.recipe import RecipeBank, BUILTIN_RECIPES


def main():
    p = argparse.ArgumentParser(description="Render a PPM image through the Fujifilm pipeline.")
    p.add_argument("input", help="input PPM (P6) file")
    p.add_argument("output", help="output PPM (P6) file")
    p.add_argument("--recipe", help="recipe slot e.g. C1 or builtin name")
    p.add_argument("--simulation", default=None, help="film simulation name")
    p.add_argument("--grain", default="OFF", help="grain roughness OFF/WEAK/STRONG")
    p.add_argument("--grain-size", default="SMALL", help="grain size SMALL/LARGE")
    p.add_argument("--clarity", type=int, default=0, help="clarity -5..5")
    p.add_argument("--chrome", default="OFF", help="color chrome level")
    p.add_argument("--chrome-blue", default="OFF", help="chrome fx blue level")
    p.add_argument("--wb-shift-r", type=int, default=0)
    p.add_argument("--wb-shift-b", type=int, default=0)
    p.add_argument("--highlight", type=int, default=0)
    p.add_argument("--shadow", type=int, default=0)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    runner_kwargs = dict(
        grain=args.grain,
        grain_size=args.grain_size,
        clarity=args.clarity,
        chrome_level=args.chrome,
        chrome_blue_level=args.chrome_blue,
        wb_shift_r=args.wb_shift_r,
        wb_shift_b=args.wb_shift_b,
        highlight=args.highlight,
        shadow=args.shadow,
        seed=args.seed,
    )

    recipe = None
    if args.recipe:
        bank = RecipeBank()
        bank.load_builtin_recipes()
        try:
            recipe = bank.get_slot(args.recipe)
        except Exception:
            recipe = None
        if recipe is None:
            # try builtin by name
            for r in BUILTIN_RECIPES.values():
                if r.name.lower() == args.recipe.lower():
                    recipe = r
                    break
        if recipe is not None:
            runner_kwargs["recipe"] = recipe
        if args.simulation is None and recipe is not None:
            runner_kwargs["simulation"] = recipe.film_simulation

    if args.simulation is not None:
        runner_kwargs["simulation"] = args.simulation

    w, h, data = PipelineRunner.read_ppm(args.input)
    runner = PipelineRunner(data, width=w, height=h, **runner_kwargs)
    out = runner.run()
    PipelineRunner.write_ppm(args.output, w, h, out)
    print(f"rendered {args.input} -> {args.output}")


if __name__ == "__main__":
    main()
