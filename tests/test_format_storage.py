"""Tests for empty FAT32 storage formatting."""

from unittest.mock import MagicMock, patch

from py_burn.model.usb import PartitionResult, UsbDevice, UsbManager


def _device() -> UsbDevice:
    return UsbDevice(
        name="sdb",
        path="/dev/sdb",  # type: ignore[arg-type]
        size_bytes=16_000_000_000,
        size_gb=16.0,
        model="TestStick",
    )


@patch.object(UsbManager, "format", return_value=True)
@patch.object(UsbManager, "partition")
@patch.object(UsbManager, "wipe", return_value=True)
@patch.object(UsbManager, "unmount_all", return_value=True)
def test_format_storage_creates_empty_fat32(
    _unmount: MagicMock,
    _wipe: MagicMock,
    partition: MagicMock,
    _format: MagicMock,
) -> None:
    partition.return_value = PartitionResult(success=True, partition_path="/dev/sdb1")
    manager = UsbManager()
    messages: list[str] = []

    result = manager.format_storage(
        _device(),
        filesystem="vfat",
        table_type="gpt",
        volume_label="PY_BURN",
        progress_callback=messages.append,
    )

    assert result.success
    partition.assert_called_once()
    assert partition.call_args.kwargs["bootable"] is False
    assert partition.call_args.kwargs["volume_label"] == "PY_BURN"
    _format.assert_called_once()
    assert "Storage ready" in messages[-1]


@patch.object(UsbManager, "unmount_all", return_value=True)
def test_format_storage_rejects_non_vfat(_unmount: MagicMock) -> None:
    manager = UsbManager()
    result = manager.format_storage(_device(), filesystem="ext4")
    assert not result.success
    assert "vfat only" in result.errors[0]
