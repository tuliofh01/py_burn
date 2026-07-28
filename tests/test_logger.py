"""Tests for TinyLogger — JSON-based logging system."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from py_burn.model.logger import LogEntry, TinyLogger


def test_log_entry_to_dict():
    """LogEntry should serialize to a dict."""
    entry = LogEntry(timestamp="2024-01-01T00:00:00", level="INFO", module="test", message="hello")
    d = entry.to_dict()
    assert d["level"] == "INFO"
    assert d["module"] == "test"
    assert d["message"] == "hello"


def test_log_entry_default_timestamp():
    """LogEntry should generate a timestamp when not provided."""
    entry = LogEntry(level="INFO", module="test", message="test")
    d = entry.to_dict()
    assert d["timestamp"] != ""


def test_tiny_logger_custom_path(tmp_path: Path):
    """TinyLogger should use a custom db path."""
    db_path = tmp_path / "test_logs.json"
    logger = TinyLogger(db_path=db_path)
    assert db_path.exists()


def test_log_and_read(tmp_path: Path):
    """Writing a log entry and reading it back should work."""
    db_path = tmp_path / "test_logs.json"
    logger = TinyLogger(db_path=db_path)
    logger.info("test", "test message", {"key": "value"})

    entries = logger.get_all()
    assert len(entries) == 1
    assert entries[0]["message"] == "test message"
    assert entries[0]["module"] == "test"
    assert entries[0]["level"] == "INFO"


def test_multiple_levels(tmp_path: Path):
    """Should support info, warning, and error levels."""
    db_path = tmp_path / "test_levels.json"
    logger = TinyLogger(db_path=db_path)
    logger.info("mod", "info msg")
    logger.warning("mod", "warn msg")
    logger.error("mod", "error msg")

    entries = logger.get_all()
    assert len(entries) == 3
    assert entries[0]["level"] == "INFO"
    assert entries[1]["level"] == "WARNING"
    assert entries[2]["level"] == "ERROR"


def test_filter_by_level(tmp_path: Path):
    """Should filter log entries by level."""
    db_path = tmp_path / "test_filter.json"
    logger = TinyLogger(db_path=db_path)
    logger.info("mod", "info")
    logger.error("mod", "error")

    errors = logger.get_by_level("ERROR")
    assert len(errors) == 1
    assert errors[0]["level"] == "ERROR"


def test_filter_by_module(tmp_path: Path):
    """Should filter log entries by module."""
    db_path = tmp_path / "test_module.json"
    logger = TinyLogger(db_path=db_path)
    logger.info("auth", "login")
    logger.info("usb", "detect")
    logger.info("auth", "logout")

    auth_entries = logger.get_by_module("auth")
    assert len(auth_entries) == 2


def test_clear(tmp_path: Path):
    """Clear should remove all entries."""
    db_path = tmp_path / "test_clear.json"
    logger = TinyLogger(db_path=db_path)
    logger.info("test", "message")
    assert logger.count() == 1
    logger.clear()
    assert logger.count() == 0


def test_count(tmp_path: Path):
    """Count should return the number of entries."""
    db_path = tmp_path / "test_count.json"
    logger = TinyLogger(db_path=db_path)
    assert logger.count() == 0
    logger.info("test", "msg1")
    logger.info("test", "msg2")
    assert logger.count() == 2
