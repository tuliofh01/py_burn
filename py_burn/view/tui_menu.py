"""Rich-based terminal view for the pyburn CLI menu."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyfiglet
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from py_burn.model.burn import BurnProgress
from py_burn.model.workflow import WorkflowField, WorkflowModel, WorkflowSection


class CLIMenu:
    """Render CLI navigation, status, banners, and live progress."""

    UNICODE = {
        "complete": "✔",
        "incomplete": "○",
        "warning": "⚠",
        "arrow": "▸",
        "back": "↩",
        "fire": "🔥",
        "iso": "💿",
        "storage": "💾",
    }

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def clear(self) -> None:
        self.console.clear()

    def render_banner(self) -> Panel:
        title = pyfiglet.figlet_format("pyburn", font="slant")
        body = Group(
            Text(title.rstrip(), style="bold cyan"),
            Align.center(Text("CLI USB writer  •  ISO burn  •  storage format", style="bold white")),
            Align.center(Text("terminal-only — no GUI", style="dim italic")),
        )
        return Panel(body, border_style="bright_blue", box=box.DOUBLE, padding=(1, 2))

    def render_breadcrumb(self, model: WorkflowModel) -> str:
        if not model.path:
            return "Home"
        labels = []
        children = model.sections
        for key in model.path:
            node = children[key]
            labels.append(f"{node.icon} {node.label}" if node.icon else node.label)
            children = node.sections
        return " › ".join(["Home", *labels])

    def render_menu(self, model: WorkflowModel) -> Panel:
        items = model.list_items()
        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE_HEAVY)
        table.add_column("#", justify="right", style="cyan", width=4)
        table.add_column("Item", style="white")
        table.add_column("Value / Status", style="dim")

        for index, (kind, key, payload) in enumerate(items, start=1):
            if kind == "section":
                section: WorkflowSection = payload
                status = self._section_status(model, key, section)
                label = f"{section.icon} {section.label}" if section.icon else section.label
                table.add_row(str(index), label, status)
            elif kind == "field":
                field: WorkflowField = payload
                section_key = model.path[-1]
                complete = model._field_is_effectively_complete(section_key, key, field)
                icon = self.UNICODE["complete"] if complete else self.UNICODE["incomplete"]
                table.add_row(str(index), field.label, f"{icon} {field.display_value()}")
            elif key == "incomplete":
                table.add_row(str(index), "Show incomplete fields", "checklist")
            elif key == "run":
                job = model.job_mode()
                label = "Burn ISO to USB" if job == "burn" else "Format empty storage"
                status = "ready" if model.is_ready() else "blocked"
                table.add_row(str(index), f"{self.UNICODE['fire']} {label}", status)
            elif key == "back":
                table.add_row(str(index), f"{self.UNICODE['back']} Back", "")
            elif key == "quit":
                table.add_row(str(index), "Quit", "")

        section = model.current_section()
        title = section.label if section and model.path else "Main Menu"
        description = section.description if section and model.path else (
            "Configure ISO, USB device, and confirmation — then run the job."
        )
        return Panel(
            Group(Text(description, style="italic"), Rule(style="bright_black"), table),
            title=f"[bold]{title}[/bold]",
            subtitle=self.render_breadcrumb(model),
            border_style="blue",
            box=box.ROUNDED,
            padding=(1, 1),
        )

    def render_incomplete(self, model: WorkflowModel) -> Panel:
        missing = model.incomplete_fields()
        if not missing:
            body = Text("All required fields are set. Confirm safety to run.", style="green")
        else:
            lines = [
                f"{self.UNICODE['incomplete']} {section}/{field}: {leaf.label}"
                for section, field, leaf in missing
            ]
            body = Text("\n".join(lines), style="yellow")
        return Panel(body, title="Incomplete checklist", border_style="yellow", box=box.ROUNDED)

    def render_iso_files(self, files: list[Path]) -> Panel:
        if not files:
            return Panel("No .iso files found in search paths.", title="ISO files", border_style="red")

        table = Table(box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("#", justify="right")
        table.add_column("Path")
        table.add_column("Size")
        for index, path in enumerate(files, start=1):
            size_gb = path.stat().st_size / 1_073_741_824
            table.add_row(str(index), str(path), f"{size_gb:.2f} GB")
        return Panel(table, title="Available ISO images", border_style="cyan")

    def render_devices(self, devices: list[Any]) -> Panel:
        if not devices:
            return Panel("No removable USB devices detected.", title="USB devices", border_style="red")

        table = Table(box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("#", justify="right")
        table.add_column("Path")
        table.add_column("Size")
        table.add_column("Model")
        for index, device in enumerate(devices, start=1):
            table.add_row(
                str(index),
                str(device.path),
                f"{device.size_gb:.1f} GB",
                device.model or "unknown",
            )
        return Panel(table, title="Detected USB devices", border_style="cyan")

    def render_message(self, title: str, message: str, *, style: str = "white") -> Panel:
        return Panel(Text(message, style=style), title=title, border_style=style, box=box.ROUNDED)

    def make_progress(self) -> Progress:
        return Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
            expand=False,
        )

    def progress_description(self, progress: BurnProgress) -> str:
        if progress.bytes_total > 0:
            done_gb = progress.bytes_done / 1_073_741_824
            total_gb = progress.bytes_total / 1_073_741_824
            return f"{progress.phase}: {progress.message} ({done_gb:.1f}/{total_gb:.1f} GB)"
        return f"{progress.phase}: {progress.message}"

    def _section_status(
        self,
        model: WorkflowModel,
        section_key: str,
        section: WorkflowSection,
    ) -> str:
        incomplete = [
            field.label
            for field_key, field in section.fields.items()
            if not model._field_is_effectively_complete(section_key, field_key, field)
        ]
        if incomplete:
            return f"{self.UNICODE['incomplete']} {len(incomplete)} pending"
        if section.fields:
            return f"{self.UNICODE['complete']} complete"
        return self.UNICODE["arrow"]

