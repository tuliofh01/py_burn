"""USB device detection, partitioning, formatting, and mount operations.

Port of the USB operations from baby_shuffus.sh (lines 351-537) into
Python 3.14 with dataclasses, pathlib, and subprocess.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


# ── Types ──────────────────────────────────────────────────────────────────

@dataclass
class UsbDevice:
    """Represents a detected USB block device."""

    name: str          # e.g. "sdb"
    path: Path         # e.g. /dev/sdb
    size_bytes: int    # total size in bytes
    size_gb: float     # total size in GB
    model: str = ""    # human-readable model name
    serial: str = ""   # serial number


@dataclass
class PartitionResult:
    """Result of partitioning and formatting."""

    success: bool
    partition_path: str = ""   # e.g. /dev/sdb1
    errors: list[str] = field(default_factory=list)


# ── Constants ──────────────────────────────────────────────────────────────

MIN_USB_GB: int = 7
USB_BUFFER_BYTES: int = 100 * 1024 * 1024  # 100 MB safety buffer
VOLUME_LABEL: str = "SHUFFUSxISO"
PARTITION_TYPE: str = "0700"  # Microsoft basic data partition


# ── USB Manager ────────────────────────────────────────────────────────────

@dataclass
class UsbManager:
    """Detects, partitions, formats, and mounts USB devices."""

    # ── Device detection ──────────────────────────────────────────────────

    def detect_devices(self) -> list[UsbDevice]:
        """Detect removable USB block devices via ``lsblk``.

        Returns a list of :class:`UsbDevice` instances. Empty list if none
        found or if ``lsblk`` is unavailable.
        """
        try:
            result = subprocess.run(
                ["lsblk", "-o", "NAME,SIZE,RM,TYPE,SERIAL,MODEL", "-d", "-n"],
                capture_output=True, text=True, timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError):
            return []

        devices: list[UsbDevice] = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            name, size_str, removable, dev_type = parts[:4]
            serial = parts[4] if len(parts) > 4 else ""
            model = " ".join(parts[5:]) if len(parts) > 5 else ""

            # Filter: must be removable (RM=1) and a disk
            if removable != "1" or dev_type != "disk":
                continue

            size_bytes = self._parse_size(size_str)
            if size_bytes == 0:
                continue

            devices.append(UsbDevice(
                name=name,
                path=Path(f"/dev/{name}"),
                size_bytes=size_bytes,
                size_gb=size_bytes / 1_073_741_824,
                model=model,
                serial=serial,
            ))

        return devices

    def get_device_info(self, device: UsbDevice) -> str:
        """Return a human-readable info string for a device."""
        return (
            f"Device: {device.path}\n"
            f"  Model: {device.model or 'unknown'}\n"
            f"  Size: {device.size_gb:.1f} GB ({device.size_bytes} bytes)\n"
            f"  Serial: {device.serial or 'N/A'}"
        )

    # ── Size validation ───────────────────────────────────────────────────

    def verify_size(self, device: UsbDevice, iso_bytes: int) -> tuple[bool, str]:
        """Check that the USB device is large enough for the ISO.

        Returns ``(ok, message)``.
        """
        if device.size_gb < MIN_USB_GB:
            return False, (
                f"USB drive too small ({device.size_gb:.1f} GB). "
                f"Minimum recommended: {MIN_USB_GB} GB."
            )

        available = device.size_bytes - USB_BUFFER_BYTES
        if iso_bytes > available:
            return False, (
                f"ISO is too large for this USB drive.\n"
                f"  ISO: {iso_bytes / 1_073_741_824:.1f} GB\n"
                f"  USB available: {available / 1_073_741_824:.1f} GB"
            )

        return True, f"Size check passed ({device.size_gb:.1f} GB drive, ISO fits)"

    # ── Unmount ────────────────────────────────────────────────────────────

    def unmount_all(self, device: UsbDevice, max_retries: int = 3) -> bool:
        """Unmount all partitions on the device with retry logic.

        Returns ``True`` if all partitions were unmounted (or none were mounted).
        """
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    ["umount", f"{device.path}*"],
                    capture_output=True, timeout=15,
                )
                # umount returns 0 even if nothing was mounted
                if result.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, OSError):
                pass

            if attempt < max_retries - 1:
                time.sleep(2)

        return False

    # ── Wipe ───────────────────────────────────────────────────────────────

    def wipe(self, device: UsbDevice) -> bool:
        """Wipe filesystem signatures and first 10 MB of the device."""
        try:
            subprocess.run(
                ["wipefs", "-a", str(device.path)],
                capture_output=True, timeout=30,
            )
            subprocess.run(
                ["dd", "if=/dev/zero", f"of={device.path}",
                 "bs=1M", "count=10"],
                capture_output=True, timeout=30,
            )
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    # ── Partition ──────────────────────────────────────────────────────────

    def partition(self, device: UsbDevice) -> PartitionResult:
        """Create a single GPT partition with Windows type (0x0700).

        Uses ``sgdisk`` (preferred) with fallback to ``gdisk``.
        """
        result = PartitionResult(success=False)

        # Try sgdisk first (modern, non-interactive)
        try:
            subprocess.run(
                ["sgdisk", "--zap-all", str(device.path)],
                capture_output=True, timeout=30,
            )
            subprocess.run(
                ["sgdisk", "-o", str(device.path)],
                capture_output=True, timeout=30,
            )
            subprocess.run(
                ["sgdisk", "-n", "1:0:0", "-t", f"1:{PARTITION_TYPE}",
                 "-c", f"1:{VOLUME_LABEL}", str(device.path)],
                capture_output=True, timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError):
            # Fallback to gdisk with input script
            try:
                gdisk_input = (
                    f"o\ny\nn\n\n\n\n{PARTITION_TYPE}\nw\ny\n"
                )
                subprocess.run(
                    ["gdisk", str(device.path)],
                    input=gdisk_input, capture_output=True,
                    timeout=30, text=True,
                )
            except (subprocess.TimeoutExpired, OSError) as e:
                result.errors.append(f"Partitioning failed: {e}")
                return result

        # Probe the new partition table
        try:
            subprocess.run(
                ["partprobe", str(device.path)],
                capture_output=True, timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass

        time.sleep(2)

        partition_path = f"{device.path}1"
        result.success = True
        result.partition_path = partition_path
        return result

    # ── Format ─────────────────────────────────────────────────────────────

    def format(self, partition: str) -> bool:
        """Format partition as FAT32 with the SHUFFUSxISO label."""
        try:
            subprocess.run(
                ["mkfs.vfat", "-F", "32", "-n", VOLUME_LABEL, partition],
                capture_output=True, timeout=60,
            )
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    # ── Mount ──────────────────────────────────────────────────────────────

    def mount_iso(self, iso_path: Path, mount_point: Path) -> bool:
        """Mount ISO file as a loop device (read-only)."""
        mount_point.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["mount", "-o", "loop,ro", str(iso_path), str(mount_point)],
                capture_output=True, timeout=15,
            )
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    def mount_usb(self, partition: str, mount_point: Path) -> bool:
        """Mount USB partition."""
        mount_point.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["mount", partition, str(mount_point)],
                capture_output=True, timeout=15,
            )
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    def unmount(self, mount_point: Path, lazy: bool = False) -> bool:
        """Unmount a mount point. Use lazy unmount as fallback."""
        try:
            result = subprocess.run(
                ["umount", str(mount_point)],
                capture_output=True, timeout=15,
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass

        if lazy:
            try:
                subprocess.run(
                    ["umount", "-l", str(mount_point)],
                    capture_output=True, timeout=15,
                )
                return True
            except (subprocess.TimeoutExpired, OSError):
                pass

        return False

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_size(size_str: str) -> int:
        """Parse lsblk size string (e.g. '119.2G', '7.5G') to bytes."""
        match = re.match(r"([\d.]+)([KMGTP]?)", size_str.strip())
        if not match:
            return 0

        value = float(match.group(1))
        unit = match.group(2)

        multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        multiplier = multipliers.get(unit, 1)
        return int(value * multiplier)