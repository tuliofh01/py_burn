"""CLI menu controller — ISO selection, device setup, burn, and storage format."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt

from py_burn.model.burn import BurnProgress, IsoBurnService
from py_burn.model.logger import TinyLogger
from py_burn.model.usb import UsbDevice, UsbManager
from py_burn.model.workflow import WorkflowField, WorkflowModel
from py_burn.view.tui_menu import CLIMenu


class CLIController:
    """Drive the interactive CLI workflow."""

    ISO_SEARCH_DIRS = (
        Path.home() / "Downloads" / "py_burn",
        Path.home() / "Downloads",
        Path.cwd(),
    )

    def __init__(
        self,
        usb_manager: UsbManager | None = None,
        burn_service: IsoBurnService | None = None,
        logger: TinyLogger | None = None,
        console: Console | None = None,
    ) -> None:
        self.console = console or Console()
        self.view = CLIMenu(self.console)
        self.model = WorkflowModel()
        self.usb_manager = usb_manager or UsbManager()
        self.burn_service = burn_service or IsoBurnService(usb_manager=self.usb_manager)
        self.logger = logger or TinyLogger()

    def run(self) -> int:
        while True:
            self.view.clear()
            self.console.print(self.view.render_banner())
            self.console.print(self.view.render_menu(self.model))

            choice = IntPrompt.ask("[bold cyan]Select[/bold cyan]", default=1, show_default=False)
            if not self._handle_choice(choice):
                return 0

    def _handle_choice(self, choice: int) -> bool:
        items = self.model.list_items()
        if choice < 1 or choice > len(items):
            self._pause("Invalid selection.")
            return True

        kind, key, payload = items[choice - 1]

        if kind == "section":
            self.model.enter(key)
            return True
        if kind == "field":
            self._edit_field(key, payload)
            return True
        if key == "back":
            self.model.back()
            return True
        if key == "incomplete":
            self._show_incomplete()
            return True
        if key == "run":
            self._run_job()
            return True
        if key == "quit":
            return False
        return True

    def _edit_field(self, field_key: str, field: WorkflowField) -> None:
        if field.readonly:
            self._pause(f"{field.label} is read-only.")
            return

        section_key = self.model.path[-1]

        if section_key == "iso" and field_key == "iso_path":
            self._pick_iso_file(field)
            return
        if section_key == "usb" and field_key == "device_path":
            self._pick_usb_device(field)
            return
        if section_key == "format" and field_key == "job_mode":
            self._set_job_mode(field)
            return

        if field.options:
            self.console.print(f"[dim]Options:[/dim] {', '.join(field.options)}")
            value = Prompt.ask(field.label, default=field.value or field.options[0])
            if value not in field.options:
                self._pause("Value must match one of the listed options.")
                return
        else:
            value = Prompt.ask(field.label, default=field.value)

        self.model.set_field(section_key, field_key, value)
        if section_key == "usb" and field_key == "device_path":
            self._sync_device_info(value)
        if section_key == "iso" and field_key == "iso_path":
            ok, message = self.model.apply_iso_profile(Path(value))
            self._pause(message if ok else f"ISO error: {message}")

    def _set_job_mode(self, field: WorkflowField) -> None:
        self.console.print(f"[dim]Options:[/dim] {', '.join(field.options)}")
        value = Prompt.ask(field.label, default=field.value or field.options[0])
        if value not in field.options:
            self._pause("Invalid job mode.")
            return
        self.model.set_field("format", "job_mode", value)
        if value == "storage_only":
            self.model.apply_storage_profile()
            self._pause("Storage-only mode — ISO is not required.")
        else:
            self.model.set_field("format", "job_mode", "iso_burn")
            iso = self.model.get_value("iso", "iso_path")
            if iso:
                ok, message = self.model.apply_iso_profile(Path(iso))
                self._pause(message if ok else message)
            else:
                self._pause("ISO burn mode — select an ISO file next.")

    def _pick_iso_file(self, field: WorkflowField) -> None:
        files: list[Path] = []
        for directory in self.ISO_SEARCH_DIRS:
            if directory.is_dir():
                files.extend(sorted(directory.glob("*.iso")))
        files = list(dict.fromkeys(files))

        self.view.clear()
        self.console.print(self.view.render_iso_files(files))

        pick = IntPrompt.ask("Select ISO # (0 = type path manually)", default=0 if not files else 1)
        if pick == 0:
            manual = Prompt.ask("ISO path", default=field.value)
            if not manual:
                self._pause()
                return
            ok, message = self.model.apply_iso_profile(Path(manual))
            self._pause(message if ok else f"ISO error: {message}")
            return

        if pick < 1 or pick > len(files):
            self._pause("Invalid ISO selection.")
            return

        ok, message = self.model.apply_iso_profile(files[pick - 1])
        self._pause(message if ok else f"ISO error: {message}")

    def _pick_usb_device(self, field: WorkflowField) -> None:
        devices = self.usb_manager.detect_devices(require_min_size=False)
        self.view.clear()
        self.console.print(self.view.render_devices(devices))

        if not devices:
            manual = Prompt.ask("Device path (or blank to cancel)", default="")
            if manual:
                self.model.set_field("usb", "device_path", manual)
                self._sync_device_info(manual)
            self._pause()
            return

        pick = IntPrompt.ask("Select device # (0 = manual entry)", default=1)
        if pick == 0:
            manual = Prompt.ask("Device path", default=field.value or str(devices[0].path))
            self.model.set_field("usb", "device_path", manual)
            self._sync_device_info(manual)
            self._pause()
            return

        if pick < 1 or pick > len(devices):
            self._pause("Invalid device selection.")
            return

        device = devices[pick - 1]
        self.model.set_field("usb", "device_path", str(device.path))
        self._sync_device_info(str(device.path), device)
        self._pause(f"Selected {device.path}")

    def _sync_device_info(self, path: str, device: UsbDevice | None = None) -> None:
        if device is None:
            device = self.usb_manager.find_device_by_path(path)
        if device is None:
            self.model.set_field("usb", "device_info", "Device not currently detected")
            return
        self.model.set_field("usb", "device_info", self.usb_manager.get_device_info(device).replace("\n", " | "))

    def _show_incomplete(self) -> None:
        self.view.clear()
        self.console.print(self.view.render_incomplete(self.model))
        self._pause()

    def _run_job(self) -> None:
        if not self.model.is_ready():
            self.view.clear()
            self.console.print(self.view.render_incomplete(self.model))
            self._pause("Complete required fields and set safety confirmation to yes.")
            return

        snapshot = self.model.snapshot()
        device = self.usb_manager.find_device_by_path(snapshot["usb_device"])
        if device is None:
            self._pause(f"Device {snapshot['usb_device']} is not available.")
            return

        if snapshot["job_mode"] == "burn":
            self._run_burn(device, snapshot)
        else:
            self._run_format(device, snapshot)

    def _run_burn(self, device: UsbDevice, snapshot: dict[str, str]) -> None:
        iso_path = Path(snapshot["iso_path"])
        self.view.clear()
        self.console.print(
            self.view.render_message(
                "Confirm ISO burn",
                self.usb_manager.require_confirmation(device, operation="burn")
                + f"\n\nISO: {iso_path}",
                style="yellow",
            )
        )
        if not Confirm.ask("Write this ISO to the USB device?", default=False):
            self._pause("Cancelled.")
            return

        self.view.clear()
        progress = self.view.make_progress()
        with progress:
            task = progress.add_task("Starting burn...", total=100)

            def on_progress(update: BurnProgress) -> None:
                progress.update(
                    task,
                    completed=update.percent,
                    description=self.view.progress_description(update),
                )

            result = self.burn_service.burn(
                device,
                iso_path,
                partition_table=snapshot["partition_table"],
                progress_callback=on_progress,
            )

        if result.success:
            self.logger.info("CLI", f"Burned {iso_path} to {device.path}")
            self._pause(f"Done. Bootable USB ready at {result.partition_path}.")
        else:
            self.logger.error("CLI", "; ".join(result.errors))
            self._pause("Burn failed:\n" + "\n".join(result.errors))

    def _run_format(self, device: UsbDevice, snapshot: dict[str, str]) -> None:
        self.view.clear()
        self.console.print(
            self.view.render_message(
                "Confirm storage format",
                self.usb_manager.require_confirmation(device, operation="format"),
                style="yellow",
            )
        )
        if not Confirm.ask("Format as empty FAT32 storage?", default=False):
            self._pause("Cancelled.")
            return

        self.view.clear()
        progress = self.view.make_progress()
        with progress:
            task = progress.add_task("Formatting...", total=100)
            step = 0

            def on_progress(message: str) -> None:
                nonlocal step
                step = min(step + 20, 95)
                progress.update(task, completed=step, description=message)

            result = self.usb_manager.format_storage(
                device,
                filesystem=snapshot["filesystem"],
                table_type=snapshot["partition_table"],
                volume_label=snapshot["volume_label"],
                progress_callback=on_progress,
            )
            progress.update(task, completed=100, description="Complete")

        if result.success:
            self.logger.info("CLI", f"Formatted {device.path} as storage")
            self._pause(f"Empty FAT32 storage ready at {result.partition_path}.")
        else:
            self.logger.error("CLI", "; ".join(result.errors))
            self._pause("Format failed:\n" + "\n".join(result.errors))

    def _pause(self, message: str = "") -> None:
        if message:
            self.console.print()
            self.console.print(self.view.render_message("CLI", message))
        Prompt.ask("\n[dim]Press Enter[/dim]", default="", show_default=False)

