"""Static-analysis CI check tests — verifies both pass and fail paths."""
import sys
from pathlib import Path

import pytest

import check_static_analysis as checker


def test_clean_store_passes_append_only_check() -> None:
    assert checker.check_append_only() == []


def test_clean_failure_log_passes_bypass_check() -> None:
    assert checker.check_bypass() == []


def test_bypass_check_fires_on_planted_fixture() -> None:
    fixture = Path(__file__).parent / "fixtures" / "bypass_violation_sample.py"
    violations = checker.check_bypass(fixture)
    assert len(violations) >= 1
    assert any("INSERT" in v.upper() for v in violations)


def test_append_only_check_fires_on_store_with_update(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tmp_path / "failure_log" / "store.py"
    bad.parent.mkdir()
    bad.write_text("class Store:\n    def update(self): pass\n")
    monkeypatch.setattr(checker, "_STORE", bad)
    monkeypatch.setattr(checker, "_ROOT", tmp_path)
    violations = checker.check_append_only()
    assert any("update" in v for v in violations)


def test_append_only_check_fires_on_store_with_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tmp_path / "failure_log" / "store.py"
    bad.parent.mkdir()
    bad.write_text("class Store:\n    def delete(self): pass\n")
    monkeypatch.setattr(checker, "_STORE", bad)
    monkeypatch.setattr(checker, "_ROOT", tmp_path)
    violations = checker.check_append_only()
    assert any("delete" in v for v in violations)


def test_bypass_check_returns_empty_list_for_empty_directory(tmp_path: Path) -> None:
    """A directory with no .py files produces no violations."""
    (tmp_path / "readme.txt").write_text("nothing here")
    violations = checker.check_bypass(tmp_path)
    assert violations == []


def test_main_exits_0_on_clean_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_static_analysis.py"])
    assert checker.main() == 0
