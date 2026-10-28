#!/usr/bin/env python3
"""ghidra_headless.py - Wrapper around Ghidra's headless analyzer for Fujifilm firmware."""

import argparse
import os
import shutil
import sys
from pathlib import Path

GHIDRA_HEADLESS = Path("/home/sergio/opt/ghidra/support/analyzeHeadless")
JAVA_DEFAULT = Path("/home/sergio/.local/share/mise/installs/java/temurin-21.0.12+101.0.LTS/bin/java")

TARGET_LANGUAGES = {
    "xt10": "ARM:LE:32:v7",
    "x10": "ARM:LE:32:v5t",
}


def discover_java() -> str:
    if os.environ.get("JAVA_HOME"):
        cand = Path(os.environ["JAVA_HOME"]) / "bin" / "java"
        if cand.is_file():
            return str(cand)
    if JAVA_DEFAULT.is_file():
        return str(JAVA_DEFAULT)
    found = shutil.which("java")
    if found:
        return found
    # mise temurin-21 fallback
    for p in Path("/home/sergio/.local/share/mise/installs/java").glob("*/bin/java"):
        if p.is_file():
            return str(p)
    return "java"


def java_home(java_bin: str) -> str:
    return str(Path(java_bin).resolve().parent.parent)


def build_command(target, bin_path, project_dir, script=None):
    return build_invocation(target, bin_path, project_dir, script)

def build_invocation(target, bin_path, project_dir, script=None):
    bin_path = Path(bin_path).resolve()
    project_dir = Path(project_dir).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    project_name = bin_path.stem or "FujifilmFirmware"

    java_bin = discover_java()
    env = dict(os.environ)
    env["JAVA_HOME"] = java_home(java_bin)
    env["PATH"] = str(Path(java_bin).parent) + os.pathsep + env.get("PATH", "")

    cmd = [
        str(GHIDRA_HEADLESS),
        str(project_dir),
        project_name,
        "-import", str(bin_path),
        "-processor", TARGET_LANGUAGES[target],
        "-overwrite",
    ]
    if script:
        script_path = Path(script).resolve()
        cmd += ["-scriptPath", str(script_path.parent), "-postScript", script_path.name]
    return env, cmd


def main():
    parser = argparse.ArgumentParser(description="Run Ghidra headless analysis on Fujifilm firmware")
    parser.add_argument("--target", choices=["xt10", "x10"], required=True)
    parser.add_argument("--bin", required=True, help="Input unpacked binary")
    parser.add_argument("--project-dir", required=True, help="Output Ghidra project directory")
    parser.add_argument("--script", help="Optional post-analysis script")
    parser.add_argument("--dry-run", action="store_true", help="Print command and env without running")
    args = parser.parse_args()

    bin_path = Path(args.bin)
    if not args.dry_run and not bin_path.exists():
        print(f"error: input binary not found: {bin_path}", file=sys.stderr)
        return 2

    env, cmd = build_invocation(args.target, bin_path, args.project_dir, args.script)

    if args.dry_run:
        print("Environment:")
        print(f"JAVA_HOME={env['JAVA_HOME']}")
        print(f"PATH={env['PATH']}")
        print("Command:")
        print(" ".join(cmd))
        return 0

    if not GHIDRA_HEADLESS.exists():
        print(f"error: analyzeHeadless not found: {GHIDRA_HEADLESS}", file=sys.stderr)
        return 2

    import subprocess
    proc = subprocess.run(cmd, env=env)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
