"""Tests for UsbManager — device detection, size validation, and partitioning."""

from __future__ import annotations

from pathlib import Path

from py_burn.model.usb import PartitionResult, UsbDevice, UsbManager


def test_usb_manager_initialization():
    """UsbManager should initialize without errors."""
    manager = UsbManager()
    assert manager is not None


def test_usb_device_dataclass():
    """UsbDevice should store device information correctly."""
    device = UsbDevice(name="sdb", path=Path("/dev/sdb"), size_bytes=16_000_000_000, size_gb=14.9)
    assert device.name == "sdb"
    assert device.path == Path("/dev/sdb")
    assert device.size_bytes == 16_000_000_000


def test_partition_result_defaults():
    """PartitionResult should have sensible defaults."""
    result = PartitionResult(success=False)
    assert not result.success
    assert result.errors == []
    assert result.partition_path == ""


def test_partition_result_with_values():
    """PartitionResult should store operation results."""
    result = PartitionResult(success=True, partition_path="/dev/sdb1", errors=["test error"])
    assert result.success
    assert result.partition_path == "/dev/sdb1"
    assert len(result.errors) == 1


def test_device_info_format():
    """get_device_info should return formatted string."""
    manager = UsbManager()
    device = UsbDevice(
        name="sdb", path=Path("/dev/sdb"),
        size_bytes=16_000_000_000, size_gb=14.9,
        model="USB Flash Drive", serial="ABC123",
    )
    info = manager.get_device_info(device)
    assert "/dev/sdb" in info
    assert "14.9" in info
    assert "USB Flash Drive" in info
    assert "ABC123" in info


def test_parse_size():
    """_parse_size should convert size strings to bytes."""
    assert UsbManager._parse_size("119.2G") == int(119.2 * 1024**3)
    assert UsbManager._parse_size("7.5G") == int(7.5 * 1024**3)
    assert UsbManager._parse_size("500M") == 500 * 1024**2
    assert UsbManager._parse_size("1T") == 1024**4
    assert UsbManager._parse_size("") == 0
    assert UsbManager._parse_size("invalid") == 0


def test_verify_size_too_small():
    """verify_size should reject drives under 7 GB."""
    manager = UsbManager()
    small_device = UsbDevice(
        name="sdb", path=Path("/dev/sdb"),
        size_bytes=4_000_000_000, size_gb=3.7,
    )
    ok, msg = manager.verify_size(small_device, 2_000_000_000)
    assert not ok
    assert "too small" in msg.lower()


def test_verify_size_iso_too_large():
    """verify_size should reject ISO that exceeds available space."""
    manager = UsbManager()
    device = UsbDevice(
        name="sdb", path=Path("/dev/sdb"),
        size_bytes=16_000_000_000, size_gb=14.9,
    )
    huge_iso = 30_000_000_000  # 30 GB ISO on 16 GB drive
    ok, msg = manager.verify_size(device, huge_iso)
    assert not ok
    assert "too large" in msg.lower()


def test_verify_size_ok():
    """verify_size should pass when ISO fits safely."""
    manager = UsbManager()
    device = UsbDevice(
        name="sdb", path=Path("/dev/sdb"),
        size_bytes=32_000_000_000, size_gb=29.8,
    )
    ok, msg = manager.verify_size(device, 4_000_000_000)
    assert ok
    assert "pass" in msg.lower()
