#!/usr/bin/env python3
"""Static-analysis CI check for the failure-logging substrate.

Two checks, both AST-based:

1. Append-only — failure_log/store.py must define no method named 'update' or 'delete'.
   Their absence is the static guarantee that no future PR can introduce a mutation
   primitive. Spot-verify manually: grep -n "def update" failure_log/store.py

2. Bypass — no .py file under the scan root may contain a raw SQL string that inserts
   directly into the 'failures' table. The only sanctioned write path is:
     log_failure() -> FailureStore.insert() -> SQLAlchemy table-insert expression.
   A raw SQL INSERT bypasses Pydantic validation and the hash chain entirely.

The bypass check scans failure_log/ by default (production code only). Pass an
explicit path to scan a different file or directory — used by tests to verify the
check fires on the planted fixture in tests/fixtures/bypass_violation_sample.py.

Exit 0: all checks pass.
Exit 1: one or more violations found (printed to stdout).

Usage (from task_h/):
    python scripts/check_static_analysis.py
    python scripts/check_static_analysis.py tests/fixtures/bypass_violation_sample.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent  # task_h/
_STORE = _ROOT / "failure_log" / "store.py"
_DEFAULT_SCAN = _ROOT / "failure_log"  # production code only

_FORBIDDEN_METHODS = {"update", "delete"}

# Matches any string literal that raw-inserts into the failures table.
_INSERT_PATTERN = re.compile(r"\bINSERT\s+INTO\s+failures\b", re.IGNORECASE)


def _is_user_file(path: Path) -> bool:
    """Skip generated, hidden, and cache directories."""
    try:
        parts = path.resolve().relative_to(_ROOT.resolve()).parts
    except ValueError:
        return True  # explicitly passed path outside _ROOT — always scan it
    return not any(
        part.startswith(".") or part in {"__pycache__", "venv", "env"}
        or part.endswith(".egg-info")
        for part in parts
    )


# ---------------------------------------------------------------------------
# Check 1 — append-only
# ---------------------------------------------------------------------------

def check_append_only() -> list[str]:
    """store.py must contain no method definition named 'update' or 'delete'."""
    if not _STORE.exists():
        return [f"MISSING: {_STORE.relative_to(_ROOT)} not found"]
    tree = ast.parse(_STORE.read_text(), filename=str(_STORE))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _FORBIDDEN_METHODS:
            violations.append(
                f"{_STORE.relative_to(_ROOT)}:{node.lineno}: "
                f"forbidden method 'def {node.name}()' in append-only store"
            )
    return violations


# ---------------------------------------------------------------------------
# Check 2 — bypass
# ---------------------------------------------------------------------------

def check_bypass(scan_root: Path | None = None) -> list[str]:
    """No .py file under scan_root may contain a raw SQL INSERT into the failures table.

    Defaults to failure_log/ (production code). Pass a specific file or directory to
    scan a different target — the test suite uses this to verify the planted fixture fires.
    """
    root = scan_root or _DEFAULT_SCAN
    files = sorted(root.rglob("*.py")) if root.is_dir() else [root]
    violations: list[str] = []
    for py_file in files:
        if py_file.is_dir() or not _is_user_file(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _INSERT_PATTERN.search(node.value):
                    violations.append(
                        f"{py_file.relative_to(_ROOT)}:{node.lineno}: "
                        f"raw SQL INSERT into 'failures' — use log_failure() instead"
                    )
    return violations


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    # Allow an explicit scan path as an optional CLI argument.
    scan_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    ao = check_append_only()
    bp = check_bypass(scan_path)
    all_v = ao + bp

    if not all_v:
        print("static-analysis: OK — all checks passed")
        return 0

    print(f"static-analysis: FAILED — {len(all_v)} violation(s)\n")
    if ao:
        print("[append-only check]")
        for v in ao:
            print(f"  {v}")
        print()
    if bp:
        print("[bypass check]")
        for v in bp:
            print(f"  {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
