#!/usr/bin/env python3
"""Thin shim to the unified CLI (re-exports patch helpers)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.patcher import encode_arm_branch, inject_payload
from cli.main import main

__all__ = ["encode_arm_branch", "inject_payload"]

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("branch", "inject"):
        sys.argv.insert(1, "patch")
    main()
