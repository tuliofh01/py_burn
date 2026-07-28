"""Tests for ISO burn orchestration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from py_burn.model.burn import BurnProgress, IsoBurnService
from py_burn.model.iso import IsoValidationResult
from py_burn.model.usb import PartitionResult, UsbDevice, UsbManager


def _device() -> UsbDevice:
    return UsbDevice(
        name="sdb",
        path=Path("/dev/sdb"),
        size_bytes=32_000_000_000,
        size_gb=32.0,
        model="TestStick",
    )


@patch.object(UsbManager, "unmount")
@patch("py_burn.model.burn.FileOperator")
@patch.object(UsbManager, "mount_usb", return_value=True)
@patch.object(UsbManager, "mount_iso", return_value=True)
@patch.object(UsbManager, "burn_iso")
@patch.object(UsbManager, "verify_size", return_value=(True, "ok"))
@patch("py_burn.model.burn.IsoValidator")
def test_burn_reports_progress(
    validator_cls: MagicMock,
    _verify_size: MagicMock,
    burn_iso: MagicMock,
    _mount_iso: MagicMock,
    _mount_usb: MagicMock,
    file_operator_cls: MagicMock,
    _unmount: MagicMock,
) -> None:
    validator_cls.return_value.validate_all.return_value = IsoValidationResult(
        success=True,
        size_bytes=1_000_000,
        size_gb=1.0,
        has_sources_dir=True,
        install_file="install.wim",
    )
    burn_iso.return_value = PartitionResult(success=True, partition_path="/dev/sdb1")

    operator = file_operator_cls.return_value
    operator.copy_standard_files.return_value = MagicMock(success=True, errors=[])
    operator.handle_install_image.return_value = MagicMock(success=True, errors=[])
    operator.sync.return_value = True
    operator.verify.return_value = MagicMock(passed=True, errors=[])

    updates: list[BurnProgress] = []
    service = IsoBurnService()
    result = service.burn(
        _device(),
        Path("/tmp/test.iso"),
        progress_callback=updates.append,
    )

    assert result.success
    assert any(update.phase == "copy" for update in updates)
    assert updates[-1].percent == 100.0
