"""Closed failure-class enumeration, loaded from config/failure_classes.json.

Adding or removing a class is a JSON edit; no code change required.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

_DATA_FILE = Path(__file__).parent.parent / "config" / "failure_classes.json"


def _load() -> dict[str, dict[str, str]]:
    with open(_DATA_FILE) as f:
        return json.load(f)  # type: ignore[no-any-return]


_DATA = _load()

FailureClass = Enum("FailureClass", {k: k for k in _DATA}, type=str)  # type: ignore[misc]

FAILURE_DEFINITIONS: dict[str, str] = {k: v["definition"] for k, v in _DATA.items()}

FAILURE_EXAMPLES: dict[str, str] = {k: v["example"] for k, v in _DATA.items()}

ALL_FAILURE_CLASSES: list[str] = list(_DATA.keys())


def validate_failure_classes(names: list[str]) -> None:
    """Raise ValueError if any name is outside the closed failure-class enumeration."""
    invalid = [n for n in names if n not in FailureClass.__members__]
    if invalid:
        raise ValueError(
            f"Unknown failure class(es) outside the closed enumeration: {invalid}. "
            f"Valid classes: {ALL_FAILURE_CLASSES}"
        )