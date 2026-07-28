"""Tests for DepsChecker — distro detection and dependency checking."""

from __future__ import annotations

from pathlib import Path

from py_burn.model.deps import DepsChecker


def test_deps_checker_initialization():
    """DepsChecker should initialize with default os-release path."""
    checker = DepsChecker()
    assert str(checker.os_release) == "/etc/os-release"


def test_detect_distro_unknown_when_no_file():
    """Should return 'unknown' when os-release doesn't exist."""
    checker = DepsChecker(os_release=Path("/tmp/nonexistent_os_release"))
    assert checker.detect_distro() == "unknown"


def test_get_distro_name_unknown():
    """Should return 'Unknown distribution' when distro is unknown."""
    checker = DepsChecker(os_release=Path("/tmp/nonexistent_os_release"))
    assert "Unknown" in checker.get_distro_name()


def test_missing_deps_on_no_os_release():
    """Should handle missing os-release gracefully."""
    checker = DepsChecker(os_release=Path("/tmp/nonexistent_os_release"))
    deps = checker.check_deps()
    assert isinstance(deps, dict)
    # Should be empty since distro is unknown (no tool map)
    assert len(deps) == 0


def test_summary_no_os_release():
    """summary() should not crash when os-release is missing."""
    checker = DepsChecker(os_release=Path("/tmp/nonexistent_os_release"))
    summary = checker.summary()
    assert isinstance(summary, str)
    assert len(summary) > 0
    assert "Unknown" in summary
