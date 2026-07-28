"""Tests for IsoDownloader — progress reporting, retries, and checksum verification."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from py_burn.model.iso_downloader import DownloadResult, IsoDownloader


def test_downloader_initialization():
    """IsoDownloader should initialize with default catalog path."""
    downloader = IsoDownloader()
    assert downloader.catalog_path.name == "iso_catalog.json"
    assert downloader.max_retries == 3


def test_load_catalog():
    """Should load and parse the ISO catalog JSON file."""
    downloader = IsoDownloader()
    catalog = downloader.load_catalog()
    assert "categories" in catalog
    assert "linux" in catalog["categories"]
    assert len(catalog["categories"]["linux"]) >= 6  # At least 6 Linux distros


def test_get_iso_info_found():
    """Should return release info for a known distro."""
    downloader = IsoDownloader()
    info = downloader.get_iso_info("ubuntu")
    assert info is not None
    assert "url" in info
    assert "label" in info


def test_get_iso_info_not_found():
    """Should return None for unknown distro."""
    downloader = IsoDownloader()
    info = downloader.get_iso_info("nonexistent_os_12345")
    assert info is None


def test_get_iso_info_release_index():
    """Should return the correct release by index."""
    downloader = IsoDownloader()
    first = downloader.get_iso_info("ubuntu", 0)
    second = downloader.get_iso_info("ubuntu", 1)
    assert first is not None
    assert second is not None
    assert first["label"] != second["label"]


@patch("py_burn.model.iso_downloader.request.urlopen")
def test_download_with_progress(mock_urlopen):
    """Download should call progress callback with bytes."""
    mock_response = MagicMock()
    mock_response.read.side_effect = [b"x" * 8192, b""]
    mock_response.__enter__.return_value = mock_response
    mock_response.headers = {"Content-Length": "8192"}
    mock_urlopen.return_value = mock_response

    downloader = IsoDownloader(download_dir=Path("/tmp/test_py_burn_dl"))
    downloader.download_dir.mkdir(parents=True, exist_ok=True)

    progress_calls: list[tuple[int, int]] = []

    def progress(current: int, total: int) -> None:
        progress_calls.append((current, total))

    result = downloader.download(
        "https://example.com/test.iso",
        filename="test.iso",
        progress_callback=progress,
    )

    assert len(progress_calls) > 0
    assert progress_calls[0][0] == 8192  # First chunk
    # Cleanup
    for f in downloader.download_dir.iterdir():
        f.unlink()
    downloader.download_dir.rmdir()


def test_download_missing_os():
    """Should return error for unknown OS."""
    downloader = IsoDownloader()
    result = downloader.download_iso("nonexistent_os")
    assert not result.success
    assert "not found" in result.error


def test_download_no_url():
    """Should handle cases where URL is None."""
    downloader = IsoDownloader()
    with patch.object(downloader, "get_iso_info") as mock:
        mock.return_value = {"label": "Test", "url": None}
        result = downloader.download_iso("test_os")
        assert not result.success
        assert "No download URL" in result.error
