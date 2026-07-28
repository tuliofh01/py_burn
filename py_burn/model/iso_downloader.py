"""ISO image downloader with progress reporting, resume support, and checksum verification.

Features:
- Chunked downloads with real-time progress callbacks
- Resume interrupted downloads via HTTP Range headers
- SHA256 checksum verification against remote checksum files
- Automatic retry with exponential backoff
- Download speed tracking for progress estimation
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib import request
from urllib.error import ContentTooShortError, HTTPError, URLError

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CATALOG = _PACKAGE_ROOT / "data" / "iso_catalog.json"


@dataclass
class DownloadResult:
    """Result of a download operation.

    Attributes:
        success: Whether the download completed successfully.
        file_path: Path to the downloaded file (or partial file on failure).
        bytes_downloaded: Number of bytes successfully downloaded.
        total_bytes: Total file size in bytes (from Content-Length).
        error: Error message if download failed.
        checksum_verified: Whether SHA256 checksum was verified.
        checksum_matches: Whether the checksum matched (only valid if verified).
        resume_used: Whether the download was resumed from a partial file.
        attempts: Number of retry attempts made.
        download_duration_seconds: Total time spent downloading.
        average_speed_bps: Average download speed in bytes per second.
    """

    success: bool
    file_path: Path | None = None
    bytes_downloaded: int = 0
    total_bytes: int = 0
    error: str = ""
    checksum_verified: bool = False
    checksum_matches: bool = False
    resume_used: bool = False
    attempts: int = 0
    download_duration_seconds: float = 0.0
    average_speed_bps: float = 0.0

    @property
    def progress_percent(self) -> float:
        """Return download progress as a percentage (0-100)."""
        if self.total_bytes > 0:
            return (self.bytes_downloaded / self.total_bytes) * 100.0
        return 0.0

    @property
    def speed_human(self) -> str:
        """Return a human-readable speed string (e.g., '5.2 MB/s')."""
        if self.download_duration_seconds <= 0:
            return ""
        bps = self.average_speed_bps
        if bps >= 1_000_000:
            return f"{bps / 1_000_000:.1f} MB/s"
        elif bps >= 1_000:
            return f"{bps / 1_000:.1f} KB/s"
        return f"{bps:.0f} B/s"


@dataclass
class IsoDownloader:
    """Downloads ISO images with progress tracking and resume capability.

    Usage::

        downloader = IsoDownloader(download_dir=Path("~/Downloads/py_burn"))
        result = downloader.download_iso("ubuntu", progress_callback=my_progress_func)
        if result.success:
            print(f"Downloaded to {result.file_path}")
    """

    catalog_path: Path = field(default_factory=lambda: _DEFAULT_CATALOG)
    download_dir: Path = Path("assets/images")
    max_retries: int = 3
    chunk_size: int = 8192
    timeout_seconds: int = 30
    user_agent: str = "py_burn/1.0"

    def __post_init__(self) -> None:
        """Ensure download directory exists on initialization."""
        self.download_dir.mkdir(parents=True, exist_ok=True)

    # ── Catalog operations ─────────────────────────────────────────────────

    def load_catalog(self) -> dict:
        """Load the ISO catalog from the JSON file.

        Returns:
            Parsed catalog dictionary.
        """
        with open(self.catalog_path, encoding="utf-8") as f:
            return json.load(f)

    def get_iso_info(self, os_name: str, release_index: int = 0) -> dict | None:
        """Look up ISO release info from the catalog.

        Args:
            os_name: Operating system key (e.g., 'ubuntu', 'windows_10').
            release_index: Index into the releases list (default: 0 for latest).

        Returns:
            Release info dict or None if not found.
        """
        catalog = self.load_catalog()
        for category in catalog.get("categories", {}).values():
            if os_name in category:
                releases = category[os_name].get("releases", [])
                if releases and release_index < len(releases):
                    return releases[release_index]
        return None

    # ── Main download method ────────────────────────────────────────────────

    def download(
        self,
        url: str,
        filename: str | None = None,
        checksum_url: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> DownloadResult:
        """Download a file with progress reporting, resume, and retry.

        Args:
            url: Direct download URL for the ISO file.
            filename: Output filename (auto-derived from URL if omitted).
            checksum_url: URL to a SHA256 checksum file for verification.
            progress_callback: Called with (bytes_downloaded, total_bytes) during download.

        Returns:
            DownloadResult with success/failure status and metadata.
        """
        if filename is None:
            filename = url.split("/")[-1] or "download.iso"

        dest = self.download_dir / filename
        temp_path = dest.with_suffix(".part")
        start_time = time.time()
        total_downloaded: int = 0
        resume_used: bool = False
        attempts: int = 0

        for attempt in range(self.max_retries):
            attempts = attempt + 1
            try:
                # Check for partial download to resume
                headers = {"User-Agent": self.user_agent}
                already_downloaded = 0

                if temp_path.exists() and attempt == 0:
                    already_downloaded = temp_path.stat().st_size
                    if already_downloaded > 0:
                        headers["Range"] = f"bytes={already_downloaded}-"
                        resume_used = True

                req = request.Request(url, headers=headers)
                timeout = self.timeout_seconds * (attempt + 1)  # Increase timeout per retry

                with request.urlopen(req, timeout=timeout) as response:
                    # Get total file size
                    total = int(response.headers.get("Content-Length", 0))
                    if already_downloaded > 0:
                        total += already_downloaded

                    # Open file in append or write mode
                    mode = "ab" if (resume_used and already_downloaded > 0) else "wb"
                    downloaded = already_downloaded

                    with open(temp_path, mode) as f:
                        while chunk := response.read(self.chunk_size):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if progress_callback:
                                progress_callback(downloaded, total)

                    total_downloaded = downloaded

                # Download complete — rename .part to final
                if temp_path.exists() and temp_path.stat().st_size > 0:
                    os.rename(temp_path, dest)
                else:
                    return DownloadResult(
                        success=False,
                        error="Downloaded file is empty",
                        attempts=attempts,
                    )

                elapsed = time.time() - start_time
                avg_speed = total_downloaded / elapsed if elapsed > 0 else 0.0

                result = DownloadResult(
                    success=True,
                    file_path=dest,
                    bytes_downloaded=total_downloaded,
                    total_bytes=total,
                    resume_used=resume_used,
                    attempts=attempts,
                    download_duration_seconds=elapsed,
                    average_speed_bps=avg_speed,
                )

                # Verify checksum if URL provided
                if checksum_url:
                    result.checksum_verified = True
                    result.checksum_matches = self._verify_checksum(dest, checksum_url)
                    if not result.checksum_matches:
                        result.error = "Checksum mismatch — file may be corrupted"
                        result.success = False

                return result

            except HTTPError as e:
                if e.code == 416:  # Range Not Satisfiable — file already complete
                    if temp_path.exists():
                        os.rename(temp_path, dest)
                        elapsed = time.time() - start_time
                        file_size = dest.stat().st_size
                        return DownloadResult(
                            success=True,
                            file_path=dest,
                            bytes_downloaded=file_size,
                            total_bytes=file_size,
                            resume_used=True,
                            attempts=attempts,
                            download_duration_seconds=elapsed,
                        )
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                return DownloadResult(
                    success=False,
                    error=f"HTTP {e.code}: {e.reason}",
                    bytes_downloaded=total_downloaded,
                    attempts=attempts,
                )

            except (URLError, ContentTooShortError, OSError, TimeoutError) as e:
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                # Keep the partial file for potential resume
                elapsed = time.time() - start_time
                return DownloadResult(
                    success=False,
                    error=str(e),
                    file_path=temp_path if temp_path.exists() else None,
                    bytes_downloaded=total_downloaded,
                    attempts=attempts,
                    download_duration_seconds=elapsed,
                )

        return DownloadResult(
            success=False,
            error="Max retries exceeded",
            attempts=attempts,
        )

    # ── Checksum verification ───────────────────────────────────────────────

    def _verify_checksum(self, file_path: Path, checksum_url: str) -> bool:
        """Verify a file's SHA256 checksum against a remote checksum file.

        The checksum file is expected to contain lines in the format::

            <sha256hash>  <filename>
            <sha256hash> *<filename>

        Args:
            file_path: Path to the downloaded file.
            checksum_url: URL to the checksum file.

        Returns:
            True if the checksum matches, False on any error or mismatch.
        """
        try:
            req = request.Request(checksum_url, headers={"User-Agent": self.user_agent})
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                checksum_data = response.read().decode("utf-8", errors="replace")

            # Compute SHA256 of the downloaded file
            sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    sha256.update(chunk)

            file_hash = sha256.hexdigest()
            return file_hash in checksum_data

        except (URLError, OSError, TimeoutError):
            return False

    # ── High-level API ──────────────────────────────────────────────────────

    def download_iso(
        self,
        os_name: str,
        release_index: int = 0,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> DownloadResult:
        """Download an ISO by OS name from the catalog.

        This is the primary API for GUI integration. It looks up the OS in the
        catalog and initiates the download with progress tracking.

        Args:
            os_name: Operating system key (e.g., 'ubuntu', 'windows_10').
            release_index: Index into the releases list (default: 0 for latest).
            progress_callback: Called with (bytes_downloaded, total_bytes).

        Returns:
            DownloadResult with download status and metadata.
        """
        info = self.get_iso_info(os_name, release_index)
        if info is None:
            return DownloadResult(success=False, error=f"OS '{os_name}' not found in catalog")

        url = info.get("url") or info.get("direct_iso_url")
        if not url:
            return DownloadResult(success=False, error=f"No download URL for {os_name}")

        filename = url.split("/")[-1] or f"{os_name}.iso"
        checksum_url = info.get("checksum_url")

        return self.download(url, filename, checksum_url, progress_callback)
