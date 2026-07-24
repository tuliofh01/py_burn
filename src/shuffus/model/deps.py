"""Cross-distro system dependency detection and reporting.

Reads /etc/os-release to identify the distribution family, maps required
system tools to their package names per distro, and checks availability
via shutil.which(). Never runs sudo or installs anything — only advises.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


type ToolMap = dict[str, str]       # tool name → package name
type DistroMap = dict[str, ToolMap]  # distro family → tool map


# ── Required system tools and their package names per distro family ────────

REQUIRED_TOOLS: DistroMap = {
    "arch": {
        "gdisk": "gdisk",
        "sgdisk": "gdisk",
        "mkfs.vfat": "dosfstools",
        "wimlib-imagex": "wimlib",
        "wimsplit": "wimlib",
        "rsync": "rsync",
        "isoinfo": "cdrtools",
        "file": "file",
        "wipefs": "util-linux",
        "partprobe": "parted",
    },
    "debian": {
        "gdisk": "gdisk",
        "sgdisk": "gdisk",
        "mkfs.vfat": "dosfstools",
        "wimlib-imagex": "wimlib",
        "wimsplit": "wimlib",
        "rsync": "rsync",
        "isoinfo": "genisoimage",
        "file": "file",
        "wipefs": "util-linux",
        "partprobe": "parted",
    },
    "redhat": {
        "gdisk": "gdisk",
        "sgdisk": "gdisk",
        "mkfs.vfat": "dosfstools",
        "wimlib-imagex": "wimlib",
        "wimsplit": "wimlib",
        "rsync": "rsync",
        "isoinfo": "cdrtools",
        "file": "file",
        "wipefs": "util-linux",
        "partprobe": "parted",
    },
    "suse": {
        "gdisk": "gdisk",
        "sgdisk": "gdisk",
        "mkfs.vfat": "dosfstools",
        "wimlib-imagex": "wimlib",
        "wimsplit": "wimlib",
        "rsync": "rsync",
        "isoinfo": "cdrtools",
        "file": "file",
        "wipefs": "util-linux",
        "partprobe": "parted",
    },
}

INSTALL_COMMANDS: dict[str, str] = {
    "arch": "sudo pacman -S gdisk dosfstools wimlib rsync cdrtools file util-linux parted",
    "debian": "sudo apt install gdisk dosfstools wimlib rsync genisoimage file util-linux parted",
    "redhat": "sudo dnf install gdisk dosfstools wimlib rsync cdrtools file util-linux parted",
    "suse": "sudo zypper install gdisk dosfstools wimlib rsync cdrtools file util-linux parted",
}


@dataclass
class DepsChecker:
    """Detects the running distro and checks system tool availability."""

    os_release: Path = Path("/etc/os-release")

    # ── Distro detection ──────────────────────────────────────────────────

    def detect_distro(self) -> str:
        """Read /etc/os-release and return the distro family.

        Returns one of: ``arch``, ``debian``, ``redhat``, ``suse``, ``unknown``.
        """
        if not self.os_release.exists():
            return "unknown"

        try:
            data = self.os_release.read_text(encoding="utf-8")
        except OSError:
            return "unknown"

        name = ""
        for line in data.splitlines():
            if line.startswith("ID="):
                name = line.removeprefix("ID=").strip('"').strip("'")
                break
            if line.startswith("ID_LIKE="):
                name = line.removeprefix("ID_LIKE=").strip('"').strip("'")
                break

        name_lower = name.lower()

        if name_lower in ("arch", "archlinux", "endeavouros", "manjaro"):
            return "arch"
        if name_lower in ("debian", "ubuntu", "linuxmint", "pop", "elementary", "zorin"):
            return "debian"
        if name_lower in ("fedora", "rhel", "centos", "rocky", "almalinux"):
            return "redhat"
        if name_lower in ("opensuse", "suse", "sles"):
            return "suse"

        return "unknown"

    # ── Dependency checking ───────────────────────────────────────────────

    def check_deps(self) -> dict[str, bool]:
        """Check every required tool via ``shutil.which()``.

        Returns a dict mapping tool name → available (``True``/``False``).
        """
        distro = self.detect_distro()
        tool_map = REQUIRED_TOOLS.get(distro, {})
        result: dict[str, bool] = {}

        for tool in tool_map:
            result[tool] = shutil.which(tool) is not None

        return result

    def missing_deps(self) -> list[str]:
        """Return a list of tool names that are not installed."""
        return [tool for tool, available in self.check_deps().items() if not available]

    # ── Install instructions ──────────────────────────────────────────────

    def get_install_instructions(self) -> str:
        """Return a distro-specific install command string."""
        distro = self.detect_distro()
        cmd = INSTALL_COMMANDS.get(distro)
        if cmd:
            return cmd
        return (
            "Unknown distribution. Please install the following packages "
            "using your package manager:\n"
            "  gdisk, dosfstools, wimlib, rsync, cdrtools/genisoimage, "
            "file, util-linux, parted"
        )

    def get_distro_name(self) -> str:
        """Return a human-readable distro name."""
        mapping = {
            "arch": "Arch Linux (or derivative)",
            "debian": "Debian / Ubuntu (or derivative)",
            "redhat": "Fedora / RHEL (or derivative)",
            "suse": "openSUSE (or derivative)",
        }
        distro = self.detect_distro()
        return mapping.get(distro, "Unknown distribution")

    # ── Summary ───────────────────────────────────────────────────────────

    def summary(self) -> str:
        """Return a human-readable dependency summary."""
        distro = self.get_distro_name()
        deps = self.check_deps()
        missing = [t for t, a in deps.items() if not a]
        present = [t for t, a in deps.items() if a]

        lines = [f"Distribution: {distro}"]
        lines.append(f"Tools found ({len(present)}): {', '.join(sorted(present))}")

        if missing:
            lines.append(f"Tools missing ({len(missing)}): {', '.join(sorted(missing))}")
            lines.append(f"Install command: {self.get_install_instructions()}")
        else:
            lines.append("All required tools are available.")

        return "\n".join(lines)