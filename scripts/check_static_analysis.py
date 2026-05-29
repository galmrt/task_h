#!/usr/bin/env python3
#!/usr/bin/env python3
"""Static-analysis CI check — two AST-based rules.

1. Append-only: ``failure_log/store.py`` must define no method named ``update`` or ``delete``.
2. Bypass: no ``.py`` file under the scan root may contain a raw SQL INSERT into the
   ``failures`` table. Sanctioned write path: ``log_failure() -> FailureStore.insert()``.

Scans ``failure_log/`` by default. Pass an explicit path to target a different file or
directory (used by tests against the planted fixture).

Exit 0 on success, exit 1 on violations.

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
_INSERT_PATTERN = re.compile(r"\bINSERT\s+INTO\s+failures\b", re.IGNORECASE)


def _is_user_file(path: Path) -> bool:
    try:
        parts = path.resolve().relative_to(_ROOT.resolve()).parts
    except ValueError:
        return True  # explicitly passed path outside _ROOT — always scan it
    return not any(
        part.startswith(".") or part in {"__pycache__", "venv", "env"}
        or part.endswith(".egg-info")
        for part in parts
    )


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


def check_bypass(scan_root: Path | None = None) -> list[str]:
    """Scan for raw SQL INSERTs into the failures table.

    Defaults to ``failure_log/``. Pass a specific path to target a different file or
    directory — the test suite uses this to verify the planted fixture fires.
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


def main() -> int:
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
