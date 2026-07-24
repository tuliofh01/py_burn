"""File copy, WIM splitting, sync, and post-copy verification.

Port of the file operations from baby_shuffus.sh (lines 547-664) into
Python 3.14 with dataclasses, pathlib, and subprocess.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


# ── Result types ───────────────────────────────────────────────────────────

@dataclass
class CopyResult:
    """Result of the file copy operation."""

    success: bool
    install_image_copied: bool = False
    install_image_split: bool = False
    split_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    """Result of post-copy verification."""

    passed: bool
    has_install_image: bool = False
    has_bootx64: bool = False
    has_bcd: bool = False
    has_bootmgr: bool = False
    install_details: str = ""
    errors: list[str] = field(default_factory=list)


# ── Constants ──────────────────────────────────────────────────────────────

FAT32_SPLIT_THRESHOLD: int = 3_500_000_000  # 3.5 GB
WIM_SPLIT_SIZE: int = 3500  # MB per split chunk


# ── File Operator ──────────────────────────────────────────────────────────

@dataclass
class FileOperator:
    """Handles file copy, WIM splitting, sync, and verification.

    Usage::

        op = FileOperator(iso_mount=Path("/tmp/iso"), usb_mount=Path("/tmp/usb"))
        copy_result = op.copy_standard_files(print)
        install_result = op.handle_install_image(print)
        op.sync()
        verify_result = op.verify()
    """

    iso_mount: Path
    usb_mount: Path

    # ── Standard file copy ─────────────────────────────────────────────────

    def copy_standard_files(
        self, progress_callback: Callable[[str], None] | None = None,
    ) -> CopyResult:
        """Copy all files from ISO to USB, excluding the large install image.

        Uses ``rsync`` with progress output. The install.wim/esd is handled
        separately by :meth:`handle_install_image`.
        """
        result = CopyResult(success=False)

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        log("Copying standard files (excluding install image)...")

        try:
            proc = subprocess.Popen(
                [
                    "rsync", "-av", "--info=progress2",
                    "--no-owner", "--no-group", "--no-perms",
                    "--exclude=sources/install.wim",
                    "--exclude=sources/install.esd",
                    f"{self.iso_mount}/",
                    f"{self.usb_mount}/",
                ],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
            )

            if proc.stdout:
                for line in proc.stdout:
                    log(line.strip())

            proc.wait(timeout=600)
            if proc.returncode != 0:
                result.errors.append(f"rsync failed with code {proc.returncode}")
                return result

        except (subprocess.TimeoutExpired, OSError) as e:
            result.errors.append(f"rsync error: {e}")
            return result

        result.success = True
        log("Standard files copied successfully.")
        return result

    # ── Install image handling ─────────────────────────────────────────────

    def handle_install_image(
        self, progress_callback: Callable[[str], None] | None = None,
    ) -> CopyResult:
        """Copy or split the Windows install image (install.wim or install.esd).

        If the file exceeds 3.5 GB, it is split into FAT32-compatible .swm
        chunks via ``wimsplit``. Otherwise it is copied directly.
        """
        result = CopyResult(success=False)

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        # Detect install file
        install_wim = self.iso_mount / "sources" / "install.wim"
        install_esd = self.iso_mount / "sources" / "install.esd"

        if install_wim.is_file():
            install_file = install_wim
            install_name = "install.wim"
        elif install_esd.is_file():
            install_file = install_esd
            install_name = "install.esd"
        else:
            result.errors.append("No install.wim or install.esd found in ISO")
            return result

        install_bytes = install_file.stat().st_size
        install_gb = install_bytes / 1_073_741_824

        log(f"Processing {install_name} ({install_gb:.1f} GB)...")

        # Create sources directory on USB
        usb_sources = self.usb_mount / "sources"
        usb_sources.mkdir(parents=True, exist_ok=True)

        if install_bytes > FAT32_SPLIT_THRESHOLD:
            # Split for FAT32 compatibility
            log(f"File exceeds 3.5 GB — splitting for FAT32 compatibility...")
            try:
                swm_base = str(usb_sources / "install.swm")
                subprocess.run(
                    ["wimsplit", str(install_file), swm_base,
                     str(WIM_SPLIT_SIZE)],
                    capture_output=True, timeout=1800,  # 30 min
                )
                result.install_image_split = True
                result.install_image_copied = True

                # Count split files
                swm_files = list(usb_sources.glob("install*.swm"))
                result.split_count = len(swm_files)
                log(f"Split into {result.split_count} .swm chunks.")

            except (subprocess.TimeoutExpired, OSError) as e:
                result.errors.append(f"WIM splitting failed: {e}")
                return result
        else:
            # Copy directly
            log(f"File fits on FAT32 — copying directly...")
            try:
                subprocess.run(
                    ["cp", str(install_file), str(usb_sources / install_name)],
                    capture_output=True, timeout=1800,
                )
                result.install_image_copied = True
                log(f"{install_name} copied successfully.")
            except (subprocess.TimeoutExpired, OSError) as e:
                result.errors.append(f"File copy failed: {e}")
                return result

        result.success = True
        return result

    # ── Sync ───────────────────────────────────────────────────────────────

    def sync(self) -> bool:
        """Flush all cached writes to disk via ``sync``."""
        try:
            subprocess.run(["sync"], timeout=120)
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    # ── Verification ───────────────────────────────────────────────────────

    def verify(self) -> VerificationResult:
        """Check that all critical boot files are present on the USB."""
        result = VerificationResult(passed=False)

        # 1. Install image
        usb_sources = self.usb_mount / "sources"

        swm_files = list(usb_sources.glob("install*.swm"))
        if swm_files:
            total = sum(f.stat().st_size for f in swm_files)
            result.has_install_image = True
            result.install_details = (
                f"{len(swm_files)}x split .swm files "
                f"({total / 1_073_741_824:.1f} GB total)"
            )
        elif (usb_sources / "install.esd").is_file():
            size = (usb_sources / "install.esd").stat().st_size
            result.has_install_image = True
            result.install_details = f"install.esd ({size / 1_073_741_824:.1f} GB)"
        elif (usb_sources / "install.wim").is_file():
            size = (usb_sources / "install.wim").stat().st_size
            result.has_install_image = True
            result.install_details = f"install.wim ({size / 1_073_741_824:.1f} GB)"
        else:
            result.errors.append("No install image found on USB")

        # 2. EFI bootloader
        bootx64 = self.usb_mount / "efi" / "boot" / "bootx64.efi"
        result.has_bootx64 = bootx64.is_file()
        if not result.has_bootx64:
            result.errors.append("EFI bootloader (bootx64.efi) not found on USB")

        # 3. BCD
        bcd1 = self.usb_mount / "efi" / "microsoft" / "boot" / "bcd"
        bcd2 = self.usb_mount / "boot" / "bcd"
        result.has_bcd = bcd1.is_file() or bcd2.is_file()
        if not result.has_bcd:
            result.errors.append("BCD not found on USB")

        # 4. bootmgr (optional — UEFI-only boot works without it)
        bootmgr = self.usb_mount / "bootmgr"
        result.has_bootmgr = bootmgr.is_file()

        result.passed = len(result.errors) == 0
        return result

    # ── Cleanup ────────────────────────────────────────────────────────────

    def cleanup(self, iso_mount: Path, usb_mount: Path) -> None:
        """Unmount and remove temporary mount points."""
        for mp in [iso_mount, usb_mount]:
            try:
                subprocess.run(
                    ["umount", "-l", str(mp)],
                    capture_output=True, timeout=15,
                )
            except (subprocess.TimeoutExpired, OSError):
                pass
            try:
                import shutil
                shutil.rmtree(mp, ignore_errors=True)
            except OSError:
                pass