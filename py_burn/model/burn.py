"""Full ISO-to-USB burn orchestration with phased progress reporting."""

from __future__ import annotations

import re
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from py_burn.model.copy import FileOperator
from py_burn.model.iso import IsoValidator
from py_burn.model.usb import UsbDevice, UsbManager

ProgressCallback = Callable[["BurnProgress"], None]


@dataclass
class BurnProgress:
    """Snapshot of burn job progress for CLI display."""

    phase: str
    percent: float
    elapsed_seconds: float
    message: str
    bytes_done: int = 0
    bytes_total: int = 0


@dataclass
class BurnResult:
    """Outcome of a full ISO burn job."""

    success: bool
    partition_path: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_RSYNC_PROGRESS = re.compile(r"(\d+)%")


@dataclass
class IsoBurnService:
    """Prepare a USB device and write a bootable ISO image to it."""

    usb_manager: UsbManager = field(default_factory=UsbManager)

    def burn(
        self,
        device: UsbDevice,
        iso_path: Path,
        *,
        partition_table: str = "gpt",
        progress_callback: ProgressCallback | None = None,
    ) -> BurnResult:
        started = time.monotonic()
        iso_path = iso_path.expanduser().resolve()

        def report(phase: str, percent: float, message: str, done: int = 0, total: int = 0) -> None:
            if progress_callback:
                progress_callback(
                    BurnProgress(
                        phase=phase,
                        percent=min(100.0, max(0.0, percent)),
                        elapsed_seconds=time.monotonic() - started,
                        message=message,
                        bytes_done=done,
                        bytes_total=total,
                    )
                )

        report("validate", 2.0, "Validating ISO image...")
        validator = IsoValidator(iso_path)
        validation = validator.validate_all()
        if not validation.success:
            return BurnResult(success=False, errors=validation.errors)

        ok, size_msg = self.usb_manager.verify_size(device, validation.size_bytes)
        if not ok:
            return BurnResult(success=False, errors=[size_msg])

        report("prepare", 8.0, f"ISO OK ({validation.size_gb:.1f} GB) — preparing USB...")

        def prep_log(message: str) -> None:
            report("prepare", 20.0, message)

        part_result = self.usb_manager.burn_iso(
            device,
            iso_path,
            progress_callback=prep_log,
            table_type=partition_table,
        )
        if not part_result.success:
            return BurnResult(success=False, errors=part_result.errors)

        iso_mount = Path(tempfile.mkdtemp(prefix="pyburn_iso_"))
        usb_mount = Path(tempfile.mkdtemp(prefix="pyburn_usb_"))
        try:
            report("mount", 28.0, "Mounting ISO and USB partition...")
            if not self.usb_manager.mount_iso(iso_path, iso_mount):
                return BurnResult(success=False, errors=["Failed to mount ISO"])
            if not self.usb_manager.mount_usb(part_result.partition_path, usb_mount):
                return BurnResult(success=False, errors=["Failed to mount USB partition"])

            operator = FileOperator(iso_mount=iso_mount, usb_mount=usb_mount)
            total_bytes = max(validation.size_bytes, 1)
            copied_bytes = 0

            def copy_log(message: str) -> None:
                nonlocal copied_bytes
                match = _RSYNC_PROGRESS.search(message)
                if match:
                    copied_bytes = int(total_bytes * int(match.group(1)) / 100)
                pct = 28.0 + (copied_bytes / total_bytes) * 62.0
                report("copy", pct, message, copied_bytes, total_bytes)

            copy_result = operator.copy_standard_files(progress_callback=copy_log)
            if not copy_result.success:
                return BurnResult(success=False, errors=copy_result.errors)

            if validation.install_file:
                report("copy", 82.0, "Copying Windows install image...", copied_bytes, total_bytes)
                install_result = operator.handle_install_image(progress_callback=copy_log)
                if not install_result.success:
                    return BurnResult(success=False, errors=install_result.errors)

            report("sync", 92.0, "Flushing writes to disk...")
            operator.sync()

            report("verify", 96.0, "Verifying boot files...")
            if validation.install_file or validation.has_sources_dir:
                verify = operator.verify()
                if not verify.passed:
                    return BurnResult(
                        success=False,
                        errors=verify.errors,
                        warnings=validation.warnings,
                    )
            else:
                report("verify", 98.0, "Linux/ live ISO — skipping Windows boot checks.")

            report("done", 100.0, "Burn complete.", total_bytes, total_bytes)
            return BurnResult(
                success=True,
                partition_path=part_result.partition_path,
                warnings=validation.warnings,
            )
        finally:
            self.usb_manager.unmount(usb_mount, lazy=True)
            self.usb_manager.unmount(iso_mount, lazy=True)
            shutil.rmtree(iso_mount, ignore_errors=True)
            shutil.rmtree(usb_mount, ignore_errors=True)
