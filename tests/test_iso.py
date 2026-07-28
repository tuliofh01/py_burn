"""Tests for IsoValidator — magic bytes, filesystem, size, and structure checks."""

from __future__ import annotations

from pathlib import Path

from py_burn.model.iso import IsoValidationResult, IsoValidator


def test_iso_validator_initialization():
    """IsoValidator should accept a path."""
    validator = IsoValidator(iso_path=Path("/tmp/test.iso"))
    assert str(validator.iso_path) == "/tmp/test.iso"


def test_validation_result_defaults():
    """IsoValidationResult should have sensible defaults."""
    result = IsoValidationResult(success=True)
    assert result.success
    assert result.errors == []
    assert result.warnings == []


def test_validation_result_failure():
    """IsoValidationResult should track errors."""
    result = IsoValidationResult(success=False, errors=["test error"])
    assert not result.success
    assert len(result.errors) == 1


def test_validate_magic_non_existent_file():
    """validate_magic should return False for non-existent files."""
    validator = IsoValidator(iso_path=Path("/tmp/nonexistent_iso_file.iso"))
    assert not validator.validate_magic()


def test_validate_filesystem_non_existent():
    """validate_filesystem should return empty string for non-existent files."""
    validator = IsoValidator(iso_path=Path("/tmp/nonexistent.iso"))
    result = validator.validate_filesystem()
    assert result == ""


def test_validate_size_non_existent():
    """validate_size should return 0 for non-existent files."""
    validator = IsoValidator(iso_path=Path("/tmp/nonexistent.iso"))
    assert validator.validate_size() == 0


def test_validate_structure_non_existent():
    """validate_structure should return False for non-existent files."""
    validator = IsoValidator(iso_path=Path("/tmp/nonexistent.iso"))
    assert not validator.validate_structure()


def test_validate_all_non_existent():
    """validate_all should return failed result for non-existent files."""
    validator = IsoValidator(iso_path=Path("/tmp/nonexistent.iso"))
    result = validator.validate_all()
    assert not result.success
    assert len(result.errors) > 0
