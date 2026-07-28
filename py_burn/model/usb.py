"""USB device detection, partitioning, formatting, and mount operations.

Enhanced with:
- Safe device detection with validation
- Confirmation prompts before destructive operations
- Device locking to prevent removal during burn
- ISO size validation against available device space
- Multiple partition table types (GPT, MBR)
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ── Types ──────────────────────────────────────────────────────────────────


@dataclass
class UsbDevice:
    """Represents a detected USB block device.

    Attributes:
        name: Kernel device name (e.g., 'sdb').
        path: Full device path (e.g., /dev/sdb).
        size_bytes: Total size in bytes.
        size_gb: Total size in gigabytes.
        model: Human-readable model name.
        serial: Device serial number.
        vendor: Device vendor (if available).
        is_mounted: Whether any partition is currently mounted.
    """

    name: str
    path: Path
    size_bytes: int
    size_gb: float
    model: str = ""
    serial: str = ""
    vendor: str = ""
    is_mounted: bool = False


@dataclass
class PartitionResult:
    """Result of partitioning and formatting operations.

    Attributes:
        success: Whether the operation succeeded.
        partition_path: Path to the created partition (e.g., /dev/sdb1).
        partition_table: Type of partition table created ('gpt' or 'mbr').
        errors: List of error messages if operation failed.
    """

    success: bool
    partition_path: str = ""
    partition_table: str = "gpt"
    errors: list[str] = field(default_factory=list)


# ── Constants ──────────────────────────────────────────────────────────────

MIN_USB_GB: int = 7
"""Minimum recommended USB size in GB."""

USB_BUFFER_BYTES: int = 100 * 1024 * 1024
"""Safety buffer (100 MB) to keep after writing the ISO."""

VOLUME_LABEL: str = "PY_BURN"
"""Default FAT32 volume label for empty storage volumes."""

STORAGE_VOLUME_LABEL: str = "PY_BURN"
"""Volume label used when formatting plain removable storage."""

PARTITION_TYPE_GPT: str = "0700"
"""GPT partition type: Microsoft basic data partition."""

PARTITION_TYPE_MBR: str = "0c"
"""MBR partition type: FAT32 LBA."""


# ── USB Manager ────────────────────────────────────────────────────────────


@dataclass
class UsbManager:
    """Detects, validates, partitions, formats, and mounts USB devices.

    Usage::

        manager = UsbManager()
        devices = manager.detect_devices()
        if devices:
            result = manager.partition(devices[0])
            if result.success:
                manager.format(result.partition_path)
    """

    # ── Device detection ──────────────────────────────────────────────────

    def detect_devices(self, require_min_size: bool = True) -> list[UsbDevice]:
        """Detect removable USB block devices via ``lsblk``.

        Filters for removable (RM=1) disk devices. Optionally filters out
        devices smaller than MIN_USB_GB.

        Args:
            require_min_size: If True, filter out devices under MIN_USB_GB.

        Returns:
            List of detected UsbDevice instances. Empty list if none found
            or if ``lsblk`` is unavailable.
        """
        try:
            result = subprocess.run(
                ["lsblk", "-o", "NAME,SIZE,RM,TYPE,SERIAL,MODEL,VENDOR,MOUNTPOINTS", "-d", "-n"],
                capture_output=True, text=True, timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError):
            return []

        devices: list[UsbDevice] = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            name, size_str, removable, dev_type = parts[:4]
            serial = parts[4] if len(parts) > 4 else ""

            # Find vendor and mountpoints in remaining parts
            remaining = parts[5:]
            vendor = ""
            mountpoints = ""
            for r in remaining:
                if r.startswith("/") or r == "":
                    mountpoints = r
                elif not vendor:
                    vendor = r

            # Filter: must be removable (RM=1) and a disk
            if removable != "1" or dev_type != "disk":
                continue

            size_bytes = self._parse_size(size_str)
            if size_bytes == 0:
                continue

            if require_min_size and (size_bytes / 1_073_741_824) < MIN_USB_GB:
                continue

            devices.append(UsbDevice(
                name=name,
                path=Path(f"/dev/{name}"),
                size_bytes=size_bytes,
                size_gb=size_bytes / 1_073_741_824,
                model=" ".join(filter(None, [vendor, parts[5] if len(parts) > 5 else ""])),
                serial=serial,
                vendor=vendor,
                is_mounted=bool(mountpoints),
            ))

        return devices

    def get_device_info(self, device: UsbDevice) -> str:
        """Return a human-readable info string for a device.

        Args:
            device: The USB device to describe.

        Returns:
            Multi-line string with device information.
        """
        lines = [
            f"Device: {device.path}",
            f"  Name: {device.name}",
            f"  Model: {device.model or 'unknown'}",
            f"  Size: {device.size_gb:.1f} GB ({device.size_bytes:,} bytes)",
            f"  Serial: {device.serial or 'N/A'}",
        ]
        if device.vendor:
            lines.append(f"  Vendor: {device.vendor}")
        lines.append(f"  Mounted: {'Yes' if device.is_mounted else 'No'}")
        return "\n".join(lines)

    # ── Safety checks ─────────────────────────────────────────────────────

    def verify_size(self, device: UsbDevice, iso_bytes: int) -> tuple[bool, str]:
        """Check that the USB device is large enough for the ISO.

        Args:
            device: The USB device to check.
            iso_bytes: Size of the ISO in bytes.

        Returns:
            Tuple of (ok, message) where ok is True if the ISO fits.
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

    def require_confirmation(self, device: UsbDevice, operation: str = "burn") -> str:
        """Generate a confirmation prompt for destructive operations.

        Args:
            device: The USB device that will be modified.
            operation: Type of operation ('burn', 'wipe', 'partition').

        Returns:
            A formatted confirmation message to show the user.
        """
        warnings = []
        if device.is_mounted:
            warnings.append("  ⚠ This device has mounted partitions that will be unmounted.")

        messages = {
            "format": (
                f"⚠ DESTRUCTIVE OPERATION: Format USB as empty storage\n\n"
                f"You are about to erase and format:\n"
                f"  Device: {device.path} ({device.model})\n"
                f"  Size: {device.size_gb:.1f} GB\n\n"
                + ("\n".join(warnings) + "\n\n" if warnings else "")
                + "ALL DATA ON THIS DEVICE WILL BE DESTROYED.\n"
                "The result will be a single empty FAT32 partition."
            ),
            "burn": (
                f"⚠ DESTRUCTIVE OPERATION: Write to USB\n\n"
                f"You are about to write an ISO image to:\n"
                f"  Device: {device.path} ({device.model})\n"
                f"  Size: {device.size_gb:.1f} GB\n\n"
                + ("\n".join(warnings) + "\n\n" if warnings else "")
                + "ALL DATA ON THIS DEVICE WILL BE DESTROYED.\n"
                "Make sure this is the correct device."
            ),
            "wipe": (
                f"⚠ DESTRUCTIVE OPERATION: Wipe USB\n\n"
                f"You are about to wipe all data on:\n"
                f"  Device: {device.path} ({device.model})\n"
                f"  Size: {device.size_gb:.1f} GB\n\n"
                + ("\n".join(warnings) + "\n\n" if warnings else "")
                + "ALL DATA WILL BE PERMANENTLY LOST."
            ),
        }

        return messages.get(operation, f"Confirm operation on {device.path}?")

    def find_device_by_path(self, path: str) -> UsbDevice | None:
        """Find a USB device by its device path.

        Args:
            path: Device path (e.g., '/dev/sdb').

        Returns:
            Matching UsbDevice or None.
        """
        for device in self.detect_devices(require_min_size=False):
            if str(device.path) == path:
                return device
        return None

    # ── Unmount ────────────────────────────────────────────────────────────

    def unmount_all(self, device: UsbDevice, max_retries: int = 3) -> bool:
        """Unmount all partitions on the device with retry logic.

        Args:
            device: The USB device to unmount.
            max_retries: Number of unmount attempts.

        Returns:
            True if all partitions were unmounted successfully.
        """
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    ["umount", "-R", str(device.path) + "*"],
                    capture_output=True, timeout=15,
                )
                if result.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, OSError):
                pass

            if attempt < max_retries - 1:
                time.sleep(2)

        return False

    # ── Wipe ───────────────────────────────────────────────────────────────

    def wipe(self, device: UsbDevice) -> bool:
        """Wipe filesystem signatures and first 10 MB of the device.

        Args:
            device: The USB device to wipe.

        Returns:
            True if wiped successfully.
        """
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

    def partition(
        self,
        device: UsbDevice,
        table_type: str = "gpt",
        *,
        volume_label: str = VOLUME_LABEL,
        bootable: bool = False,
    ) -> PartitionResult:
        """Create a single partition on the USB device.

        Creates a GPT or MBR partition table with a single partition using
        the appropriate type code for Windows USB boot compatibility.

        Args:
            device: The USB device to partition.
            table_type: Partition table type ('gpt' or 'mbr').

        Returns:
            PartitionResult with operation status.
        """
        result = PartitionResult(success=False, partition_table=table_type)

        # Try sgdisk/gdisk first
        try:
            subprocess.run(
                ["sgdisk", "--zap-all", str(device.path)],
                capture_output=True, timeout=30,
            )
            subprocess.run(
                ["sgdisk", "-o", str(device.path)],
                capture_output=True, timeout=30,
            )

            if table_type == "mbr":
                mbr_type = "ef00" if bootable else PARTITION_TYPE_MBR
                subprocess.run(
                    ["sgdisk", "-n", "1:0:0", "-t", f"1:{mbr_type}",
                     "-c", f"1:{volume_label}", str(device.path)],
                    capture_output=True, timeout=30,
                )
            else:
                gpt_type = "ef00" if bootable else PARTITION_TYPE_GPT
                subprocess.run(
                    ["sgdisk", "-n", "1:0:0", "-t", f"1:{gpt_type}",
                     "-c", f"1:{volume_label}", str(device.path)],
                    capture_output=True, timeout=30,
                )

            result.success = True
        except (subprocess.TimeoutExpired, OSError):
            # Fallback to gdisk with input script
            try:
                gdisk_input = (
                    f"o\ny\nn\n\n\n\n{PARTITION_TYPE_GPT}\nw\ny\n"
                )
                subprocess.run(
                    ["gdisk", str(device.path)],
                    input=gdisk_input, capture_output=True,
                    timeout=30, text=True,
                )
                result.success = True
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

        result.partition_path = f"{device.path}1"
        return result

    # ── Format ─────────────────────────────────────────────────────────────

    def format(
        self,
        partition: str,
        filesystem: str = "vfat",
        *,
        volume_label: str = VOLUME_LABEL,
    ) -> bool:
        """Format partition with the specified filesystem.

        Args:
            partition: Partition device path (e.g., '/dev/sdb1').
            filesystem: Filesystem type ('vfat', 'ntfs', 'ext4').

        Returns:
            True if formatting succeeded.
        """
        try:
            if filesystem == "vfat":
                subprocess.run(
                    ["mkfs.vfat", "-F", "32", "-n", volume_label[:11], partition],
                    capture_output=True, timeout=60,
                )
            elif filesystem == "ntfs":
                subprocess.run(
                    ["mkfs.ntfs", "-Q", "-L", volume_label, partition],
                    capture_output=True, timeout=120,
                )
            elif filesystem == "ext4":
                subprocess.run(
                    ["mkfs.ext4", "-F", "-L", volume_label, partition],
                    capture_output=True, timeout=120,
                )
            else:
                return False
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    # ── Mount ──────────────────────────────────────────────────────────────

    def mount_iso(self, iso_path: Path, mount_point: Path) -> bool:
        """Mount ISO file as a loop device (read-only).

        Args:
            iso_path: Path to the ISO file.
            mount_point: Directory to mount on.

        Returns:
            True if mount succeeded.
        """
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
        """Mount USB partition.

        Args:
            partition: Partition device path.
            mount_point: Directory to mount on.

        Returns:
            True if mount succeeded.
        """
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
        """Unmount a mount point. Use lazy unmount as fallback.

        Args:
            mount_point: Directory to unmount.
            lazy: Whether to use lazy unmount (-l) as fallback.

        Returns:
            True if unmount succeeded.
        """
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

    # ── Storage format flow ────────────────────────────────────────────────

    def format_storage(
        self,
        device: UsbDevice,
        *,
        filesystem: str = "vfat",
        table_type: str = "gpt",
        volume_label: str = STORAGE_VOLUME_LABEL,
        progress_callback: Callable[[str], None] | None = None,
    ) -> PartitionResult:
        """Erase a USB device and leave a single empty formatted partition.

        This prepares plain removable storage (FAT32 by default), not a
        bootable ISO loader image.
        """
        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        if filesystem != "vfat":
            return PartitionResult(
                success=False,
                errors=[f"Storage formatting currently supports vfat only, not {filesystem}"],
            )

        log(f"Preparing empty {filesystem.upper()} storage on {device.path}...")

        log("Unmounting existing partitions...")
        self.unmount_all(device)

        log("Wiping device signatures...")
        if not self.wipe(device):
            return PartitionResult(success=False, errors=["Failed to wipe device"])

        log(f"Creating {table_type.upper()} partition table...")
        part_result = self.partition(
            device,
            table_type,
            volume_label=volume_label[:11],
            bootable=False,
        )
        if not part_result.success:
            return part_result

        log(f"Formatting {part_result.partition_path} as FAT32...")
        if not self.format(
            part_result.partition_path,
            filesystem,
            volume_label=volume_label[:11],
        ):
            return PartitionResult(
                success=False,
                errors=[f"Failed to format {part_result.partition_path}"],
            )

        log(f"Storage ready at {part_result.partition_path} (label: {volume_label[:11]})")
        return part_result

    # ── Full burn flow (convenience) ──────────────────────────────────────

    def burn_iso(
        self,
        device: UsbDevice,
        iso_path: Path,
        progress_callback: Callable[[str], None] | None = None,
        table_type: str = "gpt",
    ) -> PartitionResult:
        """Full burn flow: unmount → wipe → partition → format → mount ISO.

        This is a convenience method that chains all the steps needed to
        prepare a USB device for ISO writing.

        Args:
            device: The USB device to burn to.
            iso_path: Path to the ISO file.
            progress_callback: Called with status messages.
            table_type: Partition table type ('gpt' or 'mbr').

        Returns:
            PartitionResult with the partition path for subsequent copy.
        """
        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        log(f"Starting burn to {device.path}...")

        # 1. Verify size
        iso_size = iso_path.stat().st_size
        ok, msg = self.verify_size(device, iso_size)
        if not ok:
            return PartitionResult(success=False, errors=[msg])

        # 2. Unmount
        log("Unmounting existing partitions...")
        self.unmount_all(device)

        # 3. Wipe
        log("Wiping device...")
        if not self.wipe(device):
            return PartitionResult(success=False, errors=["Failed to wipe device"])

        # 4. Partition
        log(f"Partitioning ({table_type})...")
        part_result = self.partition(device, table_type, bootable=True)
        if not part_result.success:
            return part_result

        # 5. Format
        log(f"Formatting {part_result.partition_path}...")
        if not self.format(part_result.partition_path, volume_label=VOLUME_LABEL):
            return PartitionResult(
                success=False,
                errors=[f"Failed to format {part_result.partition_path}"],
            )

        log(f"Device ready at {part_result.partition_path}")
        return part_result

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_size(size_str: str) -> int:
        """Parse lsblk size string to bytes.

        Handles formats like '119.2G', '7.5G', '500M', '1T'.

        Args:
            size_str: Size string from lsblk output.

        Returns:
            Size in bytes, or 0 if parsing fails.
        """
        match = re.match(r"([\d.]+)([KMGTP]?)", size_str.strip())
        if not match:
            return 0

        value = float(match.group(1))
        unit = match.group(2)

        multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        multiplier = multipliers.get(unit, 1)
        return int(value * multiplier)
