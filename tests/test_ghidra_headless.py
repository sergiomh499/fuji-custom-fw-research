import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "ghidra_headless.py"
SCRIPT = ROOT / "ghidra_scripts" / "LabelFujifilmStructures.py"


def test_help():
    r = subprocess.run([sys.executable, str(TOOL), "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_dry_run_xt10():
    r = subprocess.run(
        [sys.executable, str(TOOL), "--target", "xt10", "--bin", str(ROOT / "x.bin"),
         "--project-dir", str(ROOT / "proj"), "--dry-run"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "analyzeHeadless" in out
    assert "ARM:LE:32:v7" in out
    assert "JAVA_HOME" in out


def test_dry_run_x10():
    r = subprocess.run(
        [sys.executable, str(TOOL), "--target", "x10", "--bin", str(ROOT / "x.bin"),
         "--project-dir", str(ROOT / "proj"), "--dry-run"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "analyzeHeadless" in out
    assert "ARM:LE:32:v5t" in out


def test_label_script_syntax():
    py_compile.compile(str(SCRIPT), doraise=True)


if __name__ == "__main__":
    test_help()
    test_dry_run_xt10()
    test_dry_run_x10()
    test_label_script_syntax()
    print("[PASS] All Ghidra headless tests passed.")
