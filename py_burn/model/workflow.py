"""Workflow tree model for the py_burn CLI menu."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py_burn.model.iso import IsoValidator


@dataclass
class WorkflowField:
    """A single configurable value in the workflow tree."""

    label: str
    value: str = ""
    required: bool = True
    readonly: bool = False
    options: list[str] = field(default_factory=list)
    hint: str = ""

    def is_complete(self) -> bool:
        if self.readonly or not self.required:
            return True
        return bool(self.value.strip())

    def display_value(self) -> str:
        if not self.value:
            return "—"
        if len(self.value) > 48:
            return f"...{self.value[-45:]}"
        return self.value


@dataclass
class WorkflowSection:
    """A navigable group of fields."""

    label: str
    icon: str = ""
    description: str = ""
    fields: dict[str, WorkflowField] = field(default_factory=dict)
    sections: dict[str, WorkflowSection] = field(default_factory=dict)
    action: str | None = None


def default_workflow_tree() -> dict[str, WorkflowSection]:
    """Return the default nested workflow used by the CLI menu."""
    return {
        "iso": WorkflowSection(
            label="ISO Image",
            icon="💿",
            description="Pick an installer or live ISO — format settings update automatically.",
            fields={
                "iso_path": WorkflowField(
                    label="ISO file path",
                    hint="Path to .iso file or pick from recent downloads",
                ),
                "iso_info": WorkflowField(
                    label="ISO summary",
                    readonly=True,
                    required=False,
                ),
            },
        ),
        "usb": WorkflowSection(
            label="USB Device",
            icon="💾",
            description="Target removable drive — all data will be erased.",
            fields={
                "device_path": WorkflowField(
                    label="Device path",
                    hint="Pick from detected devices or enter e.g. /dev/sdb",
                ),
                "device_info": WorkflowField(
                    label="Device details",
                    readonly=True,
                    required=False,
                ),
            },
        ),
        "format": WorkflowSection(
            label="Burn Settings",
            icon="⚙",
            description="Auto-configured from the ISO; adjust only if you know what you are doing.",
            fields={
                "job_mode": WorkflowField(
                    label="Job mode",
                    value="iso_burn",
                    options=["iso_burn", "storage_only"],
                    hint="iso_burn writes a bootable image; storage_only formats empty FAT32",
                ),
                "filesystem": WorkflowField(
                    label="Filesystem",
                    value="vfat",
                    options=["vfat"],
                ),
                "partition_table": WorkflowField(
                    label="Partition table",
                    value="gpt",
                    options=["gpt", "mbr"],
                ),
                "volume_label": WorkflowField(
                    label="Volume label",
                    value="PY_BURN",
                ),
            },
        ),
        "actions": WorkflowSection(
            label="Confirm",
            icon="⚡",
            description="Review everything, then run the job.",
            fields={
                "confirmed": WorkflowField(
                    label="Safety confirmation",
                    value="no",
                    options=["no", "yes"],
                    hint="Set to yes only after verifying device and ISO",
                ),
            },
            action="run_job",
        ),
    }


@dataclass
class WorkflowModel:
    """Mutable workflow state with navigation and completeness helpers."""

    sections: dict[str, WorkflowSection] = field(default_factory=default_workflow_tree)
    path: list[str] = field(default_factory=list)

    def current_section(self) -> WorkflowSection | None:
        node: WorkflowSection | None = None
        children = self.sections
        for key in self.path:
            if node is None:
                node = children.get(key)
            else:
                node = node.sections.get(key)
            if node is None:
                return None
            children = node.sections
        if node is None and self.path:
            return None
        if node is None:
            return WorkflowSection(label="pyburn", sections=self.sections)
        return node

    def list_items(self) -> list[tuple[str, str, Any]]:
        section = self.current_section()
        if section is None:
            return []

        items: list[tuple[str, str, Any]] = []
        if not self.path:
            for key, child in section.sections.items():
                items.append(("section", key, child))
            items.append(("meta", "incomplete", None))
            items.append(("meta", "run", None))
            items.append(("meta", "quit", None))
            return items

        for key, child in section.sections.items():
            items.append(("section", key, child))
        for key, leaf in section.fields.items():
            items.append(("field", key, leaf))
        items.append(("meta", "back", None))
        return items

    def enter(self, key: str) -> bool:
        section = self.current_section()
        if section is None or key not in section.sections:
            return False
        self.path.append(key)
        return True

    def back(self) -> None:
        if self.path:
            self.path.pop()

    def get_field(self, section_key: str, field_key: str) -> WorkflowField | None:
        section = self.sections.get(section_key)
        if section is None:
            return None
        return section.fields.get(field_key)

    def set_field(self, section_key: str, field_key: str, value: str) -> None:
        leaf = self.get_field(section_key, field_key)
        if leaf is None or leaf.readonly:
            return
        leaf.value = value.strip()

    def get_value(self, section_key: str, field_key: str) -> str:
        leaf = self.get_field(section_key, field_key)
        return leaf.value if leaf else ""

    def job_mode(self) -> str:
        mode = self.get_value("format", "job_mode") or "iso_burn"
        if mode == "storage_only":
            return "storage"
        return "burn"

    def apply_iso_profile(self, iso_path: Path) -> tuple[bool, str]:
        """Validate ISO and auto-fill burn settings."""
        iso_path = iso_path.expanduser().resolve()
        if not iso_path.is_file():
            self.set_field("iso", "iso_info", "File not found")
            return False, f"ISO not found: {iso_path}"

        validation = IsoValidator(iso_path).validate_all()
        if not validation.success:
            summary = "; ".join(validation.errors) or "ISO validation failed"
            self.set_field("iso", "iso_info", summary)
            return False, summary

        parts = [
            f"{validation.size_gb:.1f} GB",
            validation.filesystem_type or "ISO9660",
        ]
        if validation.install_file:
            parts.append(f"install: {validation.install_file}")
        if validation.has_bootx64:
            parts.append("UEFI boot")
        self.set_field("iso", "iso_info", " | ".join(parts))
        self.set_field("iso", "iso_path", str(iso_path))
        self.set_field("format", "job_mode", "iso_burn")
        self.set_field("format", "filesystem", "vfat")
        self.set_field("format", "partition_table", "gpt")
        self.set_field("format", "volume_label", "PY_BURN")
        return True, "ISO loaded — burn settings updated."

    def apply_storage_profile(self) -> None:
        self.set_field("format", "job_mode", "storage_only")
        self.set_field("format", "filesystem", "vfat")
        self.set_field("format", "partition_table", "gpt")
        self.set_field("format", "volume_label", "PY_BURN")
        self.set_field("iso", "iso_path", "")
        self.set_field("iso", "iso_info", "Not used for storage-only jobs")

    def _field_is_effectively_complete(
        self,
        section_key: str,
        field_key: str,
        leaf: WorkflowField,
    ) -> bool:
        if section_key == "actions" and field_key == "confirmed":
            return leaf.value == "yes"
        if section_key == "iso" and self.job_mode() == "storage":
            return True
        return leaf.is_complete()

    def incomplete_fields(self) -> list[tuple[str, str, WorkflowField]]:
        missing: list[tuple[str, str, WorkflowField]] = []
        for section_key, section in self.sections.items():
            for field_key, leaf in section.fields.items():
                if not self._field_is_effectively_complete(section_key, field_key, leaf):
                    missing.append((section_key, field_key, leaf))
        return missing

    def is_ready(self) -> bool:
        return not self.incomplete_fields()

    def snapshot(self) -> dict[str, Any]:
        return {
            "iso_path": self.get_value("iso", "iso_path"),
            "usb_device": self.get_value("usb", "device_path"),
            "job_mode": self.job_mode(),
            "filesystem": self.get_value("format", "filesystem") or "vfat",
            "partition_table": self.get_value("format", "partition_table") or "gpt",
            "volume_label": self.get_value("format", "volume_label") or "PY_BURN",
        }

    def clone(self) -> WorkflowModel:
        return WorkflowModel(sections=deepcopy(self.sections), path=list(self.path))
