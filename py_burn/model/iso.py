"""ISO file validation — magic bytes, filesystem type, size, structure, WIM/ESD.

Port of the validation logic from baby_py_burn.sh (lines 210-344) into
Python 3.14 with dataclasses, pathlib, and subprocess.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# ── Result types ───────────────────────────────────────────────────────────

@dataclass
class IsoValidationResult:
    """Aggregated result of all ISO validation checks."""

    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Validation details
    magic_bytes_ok: bool = False
    filesystem_type: str = ""
    size_bytes: int = 0
    size_gb: float = 0.0
    isoinfo_ok: bool = False

    # Install image info
    install_file: str | None = None
    install_size_bytes: int = 0
    install_size_gb: float = 0.0
    install_needs_split: bool = False

    # Boot files
    has_sources_dir: bool = False
    has_bootx64: bool = False
    has_bcd: bool = False


# ── Constants ──────────────────────────────────────────────────────────────

ISO_MAGIC_OFFSET: int = 32769
ISO_MAGIC_EXPECTED: bytes = b"CD001"
MIN_ISO_GB: int = 1
FAT32_SPLIT_THRESHOLD: int = 3_500_000_000  # 3.5 GB


# ── Validator ──────────────────────────────────────────────────────────────

@dataclass
class IsoValidator:
    """Validates a Windows ISO file for integrity and bootability.

    Usage::

        validator = IsoValidator(Path("/path/to/windows.iso"))
        result = validator.validate_all()
        if result.success:
            print("ISO is valid")
    """

    iso_path: Path

    # ── Individual checks ─────────────────────────────────────────────────

    def validate_magic(self) -> bool:
        """Check ISO 9660 magic bytes at offset 32769."""
        try:
            with self.iso_path.open("rb") as f:
                f.seek(ISO_MAGIC_OFFSET)
                magic = f.read(5)
            return magic == ISO_MAGIC_EXPECTED
        except OSError:
            return False

    def validate_filesystem(self) -> str:
        """Run ``file --brief`` and return the type string."""
        try:
            result = subprocess.run(
                ["file", "--brief", str(self.iso_path)],
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout.strip()
            if "ISO 9660" in output:
                return output
            return ""
        except (subprocess.TimeoutExpired, OSError):
            return ""

    def validate_size(self) -> int:
        """Return file size in bytes. Returns 0 on error."""
        try:
            return self.iso_path.stat().st_size
        except OSError:
            return 0

    def validate_structure(self) -> bool:
        """Run ``isoinfo -d -i`` to verify ISO structure."""
        try:
            result = subprocess.run(
                ["isoinfo", "-d", "-i", str(self.iso_path)],
                capture_output=True, timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def validate_wim(self, wim_path: Path) -> bool:
        """Validate a WIM/ESD file via ``wimlib-imagex info``."""
        try:
            result = subprocess.run(
                ["wimlib-imagex", "info", str(wim_path)],
                capture_output=True, timeout=120,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    # ── Mounted ISO checks ────────────────────────────────────────────────

    def check_mounted(self, mount_point: Path) -> IsoValidationResult:
        """Run deeper checks on a mounted ISO.

        Call this after mounting the ISO at *mount_point*.
        """
        result = IsoValidationResult(success=True)

        # Sources directory
        sources = mount_point / "sources"
        result.has_sources_dir = sources.is_dir()
        if not result.has_sources_dir:
            result.errors.append("sources/ directory missing")

        # Install image (WIM or ESD)
        install_wim = sources / "install.wim"
        install_esd = sources / "install.esd"

        if install_esd.is_file():
            result.install_file = "install.esd"
            result.install_size_bytes = install_esd.stat().st_size
            result.install_size_gb = result.install_size_bytes / 1_073_741_824
            result.install_needs_split = result.install_size_bytes > FAT32_SPLIT_THRESHOLD
            if shutil_which("wimlib-imagex"):
                if not self.validate_wim(install_esd):
                    result.errors.append("install.esd failed WIM integrity check")
        elif install_wim.is_file():
            result.install_file = "install.wim"
            result.install_size_bytes = install_wim.stat().st_size
            result.install_size_gb = result.install_size_bytes / 1_073_741_824
            result.install_needs_split = result.install_size_bytes > FAT32_SPLIT_THRESHOLD
            if shutil_which("wimlib-imagex"):
                if not self.validate_wim(install_wim):
                    result.errors.append("install.wim failed WIM integrity check")
        else:
            result.errors.append("No install.wim or install.esd found in ISO")

        # EFI bootloader
        bootx64 = mount_point / "efi" / "boot" / "bootx64.efi"
        result.has_bootx64 = bootx64.is_file()
        if not result.has_bootx64:
            result.errors.append("EFI bootloader (efi/boot/bootx64.efi) not found")

        # BCD
        bcd1 = mount_point / "efi" / "microsoft" / "boot" / "bcd"
        bcd2 = mount_point / "boot" / "bcd"
        result.has_bcd = bcd1.is_file() or bcd2.is_file()
        if not result.has_bcd:
            result.errors.append("Boot Configuration Data (BCD) not found")

        result.success = len(result.errors) == 0
        return result

    # ── Full validation ───────────────────────────────────────────────────

    def validate_all(self) -> IsoValidationResult:
        """Run all unmounted ISO checks and return aggregated result."""
        result = IsoValidationResult(success=False)

        # 1. Magic bytes
        result.magic_bytes_ok = self.validate_magic()
        if not result.magic_bytes_ok:
            result.errors.append("Invalid ISO 9660 magic bytes — not a valid ISO image")

        # 2. Filesystem type
        result.filesystem_type = self.validate_filesystem()
        if not result.filesystem_type:
            result.errors.append("File command did not detect ISO 9660 filesystem")

        # 3. Size
        result.size_bytes = self.validate_size()
        result.size_gb = result.size_bytes / 1_073_741_824
        if result.size_bytes == 0:
            result.errors.append("Cannot read ISO file size")
        elif result.size_gb < MIN_ISO_GB:
            result.errors.append(
                f"ISO too small ({result.size_gb:.1f} GB) — likely corrupted"
            )

        # 4. ISO structure via isoinfo
        result.isoinfo_ok = self.validate_structure()
        if not result.isoinfo_ok:
            result.errors.append("isoinfo could not read the ISO structure")

        result.success = len(result.errors) == 0
        return result


# ── Helpers ────────────────────────────────────────────────────────────────

def shutil_which(cmd: str) -> bool:
    """Check if a command is available on PATH."""
    from shutil import which
    return which(cmd) is not None