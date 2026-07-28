from __future__ import annotations


from py_burn.controller.tui_controller import CLIController
from py_burn.model.container import ContainerBuilder
from py_burn.model.deps import DepsChecker
from py_burn.model.iso_downloader import IsoDownloader
from py_burn.model.logger import TinyLogger
from py_burn.model.usb import UsbManager

__version__ = "1.0.1"


class PyBurnCLI:
    """Command-line entry point for pyburn."""

    def __init__(self) -> None:
        self.logger = TinyLogger()
        self.downloader = IsoDownloader()
        self.container_builder = ContainerBuilder()
        self.deps_checker = DepsChecker()
        self.usb_manager = UsbManager()

    def run(self, args: list[str]) -> int:
        if "-h" in args or "--help" in args:
            self._print_help()
            return 0

        if not args:
            return self.run_menu()

        if "-version" in args:
            print(f"py_burn v{__version__}")
            return 0

        if "-check-deps" in args:
            return self._handle_check_deps()

        if "-list-usb" in args:
            return self._handle_list_usb()

        if "-download" in args:
            return self._handle_download(args)

        if "-status" in args or "-cli" in args:
            return self._handle_status()

        if "-container_build" in args:
            return self._handle_container_build(args)

        if args[0].startswith("-"):
            print(f"Unknown flag: {args[0]}")
            self._print_help()
            return 1

        return self.run_menu()

    def run_menu(self) -> int:
        controller = CLIController(usb_manager=self.usb_manager, logger=self.logger)
        return controller.run()

    def _print_help(self) -> None:
        print("py_burn — CLI USB tool for Linux")
        print()
        print("Usage:")
        print("  py_burn                 Interactive CLI menu (default)")
        print("  py_burn -status          Show deps and detected USB devices")
        print("  py_burn -download <os>   Download an official ISO")
        print("  py_burn -check-deps      Check required system tools")
        print("  py_burn -list-usb        List removable USB devices")
        print("  py_burn -version         Show version")
        print("  py_burn -h               Show this help")
        print()
        print("Alias: pyburn (same commands)")
        print()
        print("Destructive operations (burn / format) require sudo.")

    def _handle_status(self) -> int:
        print("pyburn status")
        print()
        print(self.deps_checker.summary())
        print()
        devices = self.usb_manager.detect_devices(require_min_size=False)
        if devices:
            print(f"Detected {len(devices)} USB device(s):")
            for dev in devices:
                print(f"  {dev.path} — {dev.size_gb:.1f} GB ({dev.model})")
        else:
            print("No USB devices detected.")
        return 0

    def _handle_container_build(self, args: list[str]) -> int:
        container_type = args[1] if len(args) > 1 else "docker"
        dockerfile = (
            "FROM python:3.14-slim\n"
            "WORKDIR /app\n"
            "COPY . .\n"
            "RUN pip install poetry && poetry install\n"
            "CMD [\"pyburn\"]\n"
        )
        result = self.container_builder.build(container_type, dockerfile)
        if result.success:
            print(f"Container build initiated: {result.image_name}")
            self.logger.info("CLI", f"Container build: {result.image_name}")
            return 0
        print(f"Container build failed: {'; '.join(result.errors)}")
        self.logger.error("CLI", f"Container build failed: {'; '.join(result.errors)}")
        return 1

    def _handle_check_deps(self) -> int:
        print(self.deps_checker.summary())
        missing = self.deps_checker.missing_deps()
        if missing:
            print(f"\nInstall missing tools: {self.deps_checker.get_install_instructions()}")
            return 1
        return 0

    def _handle_list_usb(self) -> int:
        devices = self.usb_manager.detect_devices(require_min_size=False)
        if not devices:
            print("No USB devices detected.")
            return 1
        for dev in devices:
            print(self.usb_manager.get_device_info(dev))
            print()
        return 0

    def _handle_download(self, args: list[str]) -> int:
        index = args.index("-download")
        os_name = args[index + 1] if len(args) > index + 1 else "ubuntu"

        def progress(current: int, total: int) -> None:
            if total > 0:
                pct = int(current / total * 100)
                print(
                    f"\rDownloading: {pct}% "
                    f"({current / 1024 / 1024:.1f} MB / {total / 1024 / 1024:.1f} MB)",
                    end="",
                )

        result = self.downloader.download_iso(os_name, progress_callback=progress)
        print()
        if result.success:
            print(f"Downloaded to: {result.file_path}")
            self.logger.info("CLI", f"Downloaded {os_name} to {result.file_path}")
            return 0
        print(f"Download failed: {result.error}")
        self.logger.error("CLI", f"Download failed: {result.error}")
        return 1

