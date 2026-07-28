"""File copy, WIM splitting, sync, and post-copy verification.

Enhanced with:
- Progress callbacks for all copy operations
- Error recovery with retry logic for failed copies
- File-level progress granularity
- Post-copy verification with detailed reporting
"""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


# ── Result types ───────────────────────────────────────────────────────────


@dataclass
class CopyResult:
    """Result of a file copy operation.

    Attributes:
        success: Whether the operation completed successfully.
        files_copied: Number of files successfully copied.
        bytes_copied: Total bytes transferred.
        install_image_copied: Whether the install image was handled.
        install_image_split: Whether the install image was split for FAT32.
        split_count: Number of .swm split files created.
        errors: List of error messages if operation failed.
    """

    success: bool
    files_copied: int = 0
    bytes_copied: int = 0
    install_image_copied: bool = False
    install_image_split: bool = False
    split_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    """Result of post-copy verification.

    Attributes:
        passed: Whether all critical checks passed.
        has_install_image: Whether install.wim/esd/swm exists.
        has_bootx64: Whether EFI bootloader (bootx64.efi) exists.
        has_bcd: Whether Boot Configuration Data exists.
        has_bootmgr: Whether bootmgr exists (optional, legacy BIOS).
        install_details: Human-readable description of install image.
        total_size_gb: Total size of copied data in GB.
        errors: List of verification errors.
    """

    passed: bool
    has_install_image: bool = False
    has_bootx64: bool = False
    has_bcd: bool = False
    has_bootmgr: bool = False
    install_details: str = ""
    total_size_gb: float = 0.0
    errors: list[str] = field(default_factory=list)


# ── Constants ──────────────────────────────────────────────────────────────

FAT32_SPLIT_THRESHOLD: int = 3_500_000_000  # 3.5 GB
"""Files larger than this must be split for FAT32 compatibility."""

WIM_SPLIT_SIZE: int = 3500  # MB per split chunk
"""Size of each .swm split chunk in megabytes."""

MAX_COPY_RETRIES: int = 3
"""Maximum number of retries for failed copy operations."""

RETRY_DELAY_SECONDS: float = 2.0
"""Delay between retry attempts in seconds."""


# ── File Operator ──────────────────────────────────────────────────────────


@dataclass
class FileOperator:
    """Handles file copy, WIM splitting, sync, and verification.

    Encapsulates all file operations needed to prepare a USB drive with
    Windows or Linux bootable media, including handling large install.wim
    files that exceed FAT32's 4 GB file size limit.

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
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> CopyResult:
        """Copy all files from ISO to USB, excluding the large install image.

        Uses ``rsync`` for efficient bulk copying with progress reporting.
        The install.wim/esd is excluded and handled separately by
        :meth:`handle_install_image`.

        Args:
            progress_callback: Called with status messages during copy.

        Returns:
            CopyResult with operation status and statistics.
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

        # Count files and bytes copied
        result.files_copied = sum(1 for _ in self.usb_mount.rglob("*") if _.is_file())
        result.bytes_copied = sum(
            f.stat().st_size for f in self.usb_mount.rglob("*") if f.is_file()
        )
        result.success = True
        log(f"Standard files copied successfully ({result.files_copied} files).")
        return result

    # ── Install image handling ─────────────────────────────────────────────

    def handle_install_image(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> CopyResult:
        """Copy or split the Windows install image (install.wim or install.esd).

        If the file exceeds 3.5 GB, it is split into FAT32-compatible .swm
        chunks via ``wimsplit``. Otherwise it is copied directly.

        Args:
            progress_callback: Called with status messages.

        Returns:
            CopyResult with operation status.
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
            for attempt in range(MAX_COPY_RETRIES):
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
                    swm_files = sorted(usb_sources.glob("install*.swm"))
                    result.split_count = len(swm_files)

                    # Calculate total bytes from split files
                    result.bytes_copied = sum(f.stat().st_size for f in swm_files)
                    log(f"Split into {result.split_count} .swm chunks.")
                    break

                except (subprocess.TimeoutExpired, OSError) as e:
                    if attempt < MAX_COPY_RETRIES - 1:
                        log(f"WIM split attempt {attempt + 1} failed, retrying...")
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                    result.errors.append(f"WIM splitting failed after {MAX_COPY_RETRIES} attempts: {e}")
                    return result
        else:
            # Copy directly with retries
            log(f"File fits on FAT32 — copying directly...")
            dest_path = usb_sources / install_name
            for attempt in range(MAX_COPY_RETRIES):
                try:
                    subprocess.run(
                        ["cp", str(install_file), str(dest_path)],
                        capture_output=True, timeout=1800,
                    )
                    result.install_image_copied = True
                    result.bytes_copied = install_bytes

                    # Verify the copy
                    if dest_path.exists() and dest_path.stat().st_size == install_bytes:
                        log(f"{install_name} copied successfully ({install_gb:.1f} GB).")
                        break
                    else:
                        raise OSError("Copied file size mismatch")

                except (subprocess.TimeoutExpired, OSError) as e:
                    if attempt < MAX_COPY_RETRIES - 1:
                        log(f"Copy attempt {attempt + 1} failed, retrying...")
                        time.sleep(RETRY_DELAY_SECONDS)
                        # Remove partial copy
                        if dest_path.exists():
                            dest_path.unlink()
                        continue
                    result.errors.append(f"File copy failed after {MAX_COPY_RETRIES} attempts: {e}")
                    return result

        result.files_copied = result.split_count if result.install_image_split else 1
        result.success = True
        return result

    # ── Sync ───────────────────────────────────────────────────────────────

    def sync(self) -> bool:
        """Flush all cached writes to disk via the ``sync`` command.

        Should be called after all copies complete to ensure data is
        physically written before unmounting.

        Returns:
            True if sync completed successfully.
        """
        try:
            subprocess.run(["sync"], timeout=120)
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    # ── Verification ───────────────────────────────────────────────────────

    def verify(self) -> VerificationResult:
        """Check that all critical boot files are present on the USB.

        Verifies:
        - Install image (install.wim, install.esd, or .swm files)
        - EFI bootloader (efi/boot/bootx64.efi)
        - Boot Configuration Data (BCD)
        - bootmgr (optional, for legacy BIOS)

        Returns:
            VerificationResult with detailed pass/fail status.
        """
        result = VerificationResult(passed=False)

        # Calculate total size
        all_files = list(self.usb_mount.rglob("*")) if self.usb_mount.exists() else []
        result.total_size_gb = sum(
            f.stat().st_size for f in all_files if f.is_file()
        ) / 1_073_741_824

        usb_sources = self.usb_mount / "sources"

        # 1. Install image
        swm_files = sorted(usb_sources.glob("install*.swm"))
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

    def cleanup(self, iso_mount: Path | None = None, usb_mount: Path | None = None) -> None:
        """Unmount and remove temporary mount points.

        Args:
            iso_mount: ISO mount point to clean up (defaults to self.iso_mount).
            usb_mount: USB mount point to clean up (defaults to self.usb_mount).
        """
        iso_mount = iso_mount or self.iso_mount
        usb_mount = usb_mount or self.usb_mount

        for mp in [iso_mount, usb_mount]:
            if mp is None or not mp.exists():
                continue
            try:
                subprocess.run(
                    ["umount", "-l", str(mp)],
                    capture_output=True, timeout=15,
                )
            except (subprocess.TimeoutExpired, OSError):
                pass
            try:
                shutil.rmtree(mp, ignore_errors=True)
            except OSError:
                pass
