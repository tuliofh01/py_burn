"""Tests for FileOperator — file copy, WIM splitting, and verification."""

from __future__ import annotations

from pathlib import Path

from py_burn.model.copy import CopyResult, FileOperator, VerificationResult


def test_file_operator_initialization():
    """FileOperator should accept mount paths."""
    op = FileOperator(iso_mount=Path("/tmp/iso"), usb_mount=Path("/tmp/usb"))
    assert str(op.iso_mount) == "/tmp/iso"
    assert str(op.usb_mount) == "/tmp/usb"


def test_copy_result_defaults():
    """CopyResult should have sensible defaults."""
    result = CopyResult(success=False)
    assert not result.success
    assert result.errors == []


def test_copy_result_success():
    """CopyResult should report success."""
    result = CopyResult(success=True, install_image_copied=True)
    assert result.success
    assert result.install_image_copied
    assert not result.install_image_split


def test_verification_result_defaults():
    """VerificationResult should have sensible defaults."""
    result = VerificationResult(passed=False)
    assert not result.passed
    assert result.errors == []


def test_verification_result_pass():
    """VerificationResult should report pass."""
    result = VerificationResult(passed=True, has_install_image=True, has_bootx64=True, has_bcd=True)
    assert result.passed
    assert result.has_install_image
    assert result.has_bootx64
    assert result.has_bcd


def test_handle_install_image_no_files():
    """Should return error when no install image exists."""
    op = FileOperator(iso_mount=Path("/tmp/nonexistent_iso"), usb_mount=Path("/tmp/nonexistent_usb"))
    result = op.handle_install_image()
    assert not result.success
    assert any("No install" in e for e in result.errors)


def test_copy_standard_files_no_source():
    """Should return error when source doesn't exist."""
    op = FileOperator(iso_mount=Path("/tmp/nonexistent_iso"), usb_mount=Path("/tmp/nonexistent_usb"))
    result = op.copy_standard_files()
    assert not result.success


def test_verify_no_files():
    """Verify should fail when no files are present."""
    op = FileOperator(iso_mount=Path("/tmp/iso"), usb_mount=Path("/tmp/usb"))
    result = op.verify()
    assert not result.passed
    assert len(result.errors) > 0
