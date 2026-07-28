from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class LogEntry:
    timestamp: str = ""
    level: str = "INFO"
    module: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
            "level": self.level,
            "module": self.module,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class TinyLogger:
    db_path: Path = Path("assets/dependencies/py_burn_logs.json")
    max_entries: int = 10000

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            self._write([])

    def _read(self) -> list[dict[str, Any]]:
        try:
            with open(self.db_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, entries: list[dict[str, Any]]) -> None:
        with open(self.db_path, "w") as f:
            json.dump(entries, f, indent=2)

    def log(self, level: str, module: str, message: str, details: dict[str, Any] | None = None) -> None:
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level.upper(),
            module=module,
            message=message,
            details=details or {},
        )
        entries = self._read()
        entries.append(entry.to_dict())
        if len(entries) > self.max_entries:
            entries = entries[-self.max_entries:]
        self._write(entries)

    def info(self, module: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.log("INFO", module, message, details)

    def warning(self, module: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.log("WARNING", module, message, details)

    def error(self, module: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.log("ERROR", module, message, details)

    def get_all(self, limit: int = 100) -> list[dict[str, Any]]:
        entries = self._read()
        return entries[-limit:]

    def get_by_level(self, level: str, limit: int = 100) -> list[dict[str, Any]]:
        entries = self._read()
        filtered = [e for e in entries if e.get("level", "").upper() == level.upper()]
        return filtered[-limit:]

    def get_by_module(self, module: str, limit: int = 100) -> list[dict[str, Any]]:
        entries = self._read()
        filtered = [e for e in entries if e.get("module", "") == module]
        return filtered[-limit:]

    def clear(self) -> None:
        self._write([])

    def count(self) -> int:
        return len(self._read())