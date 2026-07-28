<h1 align="center">py_burn</h1>

<p align="center">
  <strong>
    Open-source Linux USB tool — format drives, burn bootable ISOs, skip the Rufus reboot.
  </strong>
</p>

<p align="center">
  <img
    src="https://www.python.org/static/community_logos/python-powered-w-200x80.png"
    alt="Python powered logo — pyburn is a Python 3.14 open-source USB utility for Linux"
    width="200"
  />
</p>

<div align="center">

<pre>
  ____  _   _ ____    _   _ ____  _   _ 
 |  _ \| | | |  _ \  | | | | __ )| \ | |
 | |_) | |_| | |_) | | | | |  _ \|  \| |
 |  __/|  _  |  __/  | |_| | |_) | |\  |
 |_|   |_| |_|_|      \___/|____/|_| \_|

CLI USB writer — format · burn · boot
</pre>

</div>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=for-the-badge" alt="MIT open source license"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.14+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.14 or newer"></a>
  <img src="https://img.shields.io/badge/platform-Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black" alt="Linux USB bootable drive creator">
  <img src="https://img.shields.io/badge/Rufus-alternative-ff6b35?style=for-the-badge" alt="Rufus alternative for Linux">
</p>

<p align="center">
  <a href="#-what-is-pyburn">About</a> ·
  <a href="#-features">Features</a> ·
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-format-a-usb-drive-for-storage-cli-menu">Format USB</a> ·
  <a href="#-create-a-bootable-linux-or-windows-usb">Burn ISO</a> ·
  <a href="#-how-iso-burning-works">How ISO Burning Works</a> ·
  <a href="#-architecture">Architecture</a> ·
  <a href="#-how-this-project-is-built">How it's built</a> ·
  <a href="#-dependencies">Dependencies</a> ·
  <a href="#-cli-reference">CLI reference</a> ·
  <a href="#-open-source--mit-license">License</a> ·
  <a href="#-faq">FAQ</a>
</p>

---

## 🔥 What is pyburn?

**pyburn** (`py_burn`) is a **terminal-only**, **open-source**, **MIT-licensed** CLI for Linux that helps you:

- **Format USB drives** as empty FAT32 storage
- **Create bootable USB sticks** from Linux and Windows ISO files
- **Download official ISOs** without hunting mirror pages
- **Replace Rufus** when you live on Linux and do not want a Windows VM just to flash a stick

No mystery binaries. No vendor lock-in. Fork it, read it, improve it — that is the point.

> **TL;DR:** Plug USB → pick mode → confirm → done. Your future self thanks you.

---

## ✨ Features

| What you need | What pyburn does |
|---|---|
| **Rufus alternative on Linux** | Interactive CLI menu for USB format and ISO burn |
| **Format USB to FAT32** | Wipe, partition, and label a blank storage drive |
| **Bootable Linux USB** | Validate ISO, prepare partition, copy live/installer files |
| **Bootable Windows USB** | Handles large `install.wim` splits for FAT32 limits |
| **ISO downloader** | Curated catalog: Arch, Ubuntu, Fedora, Debian, and more |
| **Dependency checker** | Tells you exactly which packages your distro is missing |
| **Safety first** | Confirmations, incomplete-field checks, device warnings |

**Commands** — primary name is `py_burn`; `pyburn` is an alias. All flags use a leading hyphen (`-`).

| Command | What it does |
|---|---|
| `sudo poetry run py_burn` | **Interactive CLI menu** (default) — burn ISO or format storage |
| `poetry run py_burn -h` | Show help |
| `poetry run py_burn -version` | Show version |
| `poetry run py_burn -status` | Show dependencies and detected USB devices |
| `poetry run py_burn -check-deps` | Audit required system tools |
| `poetry run py_burn -list-usb` | List removable USB devices |
| `poetry run py_burn -download <os>` | Download an official ISO |

---

## 🚀 Quick Start

### Install

```bash
git clone https://github.com/tuliofh01/py_burn.git
cd py_burn
poetry install          # creates .venv and installs dependencies
poetry run py_burn -check-deps
```

### Try it in 30 seconds

```bash
# See your USB drives
poetry run py_burn -list-usb

# Launch the interactive CLI menu (burn ISO or format storage)
sudo poetry run py_burn
```

> Destructive steps need `sudo`. When in doubt, run `poetry run py_burn -list-usb` first. Trust, but verify `/dev/sdX`.

---

## 🛠️ How this project is built

pyburn is a **plain Python CLI** — no compiled extensions, no GUI framework, no mystery build chain. What you see in the repo is what runs on your machine. The tooling around it exists to keep dependencies reproducible and the dev environment isolated from your system Python.

### The stack at a glance

| Piece | What it is | What it implies for you |
|---|---|---|
| **Python 3.14** | The language runtime | You need 3.14+ installed. pyburn uses modern Python (dataclasses, type hints, `pathlib`). |
| **Poetry** | Dependency and project manager | Run commands via `poetry run …` or activate the venv first. Do not `pip install` into system Python. |
| **`.venv/`** | Local virtual environment | A sandboxed copy of Python + packages, created inside the repo. Safe to delete and recreate with `poetry install`. |
| **`pyproject.toml`** | Project manifest | Declares package name, version, Python deps, CLI entry points (`py_burn`, `pyburn`), and dev tools (pytest, ruff). |
| **`poetry.lock`** | Frozen dependency graph | Exact versions Poetry resolved. Commit this — everyone gets the same installs. |
| **`poetry.toml`** | Poetry settings | `in-project = true` means the venv lives at `.venv/` in the repo root, not somewhere global. |
| **`requirements.txt`** | Pip-compatible pin list | Same runtime versions as the lockfile, for Docker, CI, or `pip install -r requirements.txt` without Poetry. |
| **`pyburn.py`** | Root launcher | Thin wrapper that calls `py_burn.__main__`. Handy when you are not inside the venv. |
| **`Dockerfile` + `build-docker.sh`** | Container image | Packages pyburn + Linux system tools into an image. USB access still needs `--privileged` and `/dev` mounted. |

### Poetry — why it is here

**Poetry** is a Python tool that manages three things in one place:

1. **Dependencies** — what libraries pyburn needs (`rich`, `tinydb`, `pyfiglet`)
2. **The virtual environment** — where those libraries get installed
3. **The installable package** — so `py_burn` becomes a command you can run

When you run:

```bash
poetry install
```

Poetry reads `pyproject.toml`, creates `.venv/` (because of `poetry.toml`), installs locked versions from `poetry.lock`, and registers the `py_burn` / `pyburn` console scripts.

**What that implies:** you do not need to manually create a venv or guess package versions. `poetry install` is the one command that sets up a working dev environment. Use `poetry add <package>` to add deps and `poetry run pytest` to run tools inside the venv without activating it.

### Virtual environment (`.venv`) — what it is

A **virtual environment** is an isolated Python installation. Packages you install for pyburn stay inside `.venv/` and do not pollute `/usr/bin/python` or break other projects.

```text
System Python          .venv/ (project-local)
─────────────          ─────────────────────
/usr/bin/python3   ≠   py_burn/.venv/bin/python
global pip packages    only pyburn's dependencies
```

**What that implies:**

- `.venv/` is **gitignored** — each clone builds its own
- After `poetry install`, either run `poetry run py_burn` **or** activate first:

```bash
source .venv/bin/activate   # now `py_burn` works directly
py_burn -list-usb
deactivate                  # leave the venv
```

- If installs act weird, nuke and recreate: `rm -rf .venv && poetry install`

### `pyproject.toml` vs `poetry.lock` vs `requirements.txt`

These three files answer different questions:

| File | Answers | Who cares |
|---|---|---|
| `pyproject.toml` | *What* does the project need? (ranges like `rich ^14.0`) | Authors editing dependencies |
| `poetry.lock` | *Exactly which* versions were resolved? | Everyone cloning the repo — **commit this** |
| `requirements.txt` | Same pins, pip-friendly format | Docker, CI, or pip-only workflows |

**What that implies:** day-to-day development uses Poetry. If you only have pip, `pip install -r requirements.txt && pip install .` works for runtime, but Poetry is the canonical path.

### Dev workflow

```bash
git clone https://github.com/tuliofh01/py_burn.git
cd py_burn
poetry install              # create .venv + install deps + register CLI

poetry run py_burn -check-deps
poetry run pytest           # run tests
poetry run ruff check py_burn tests   # lint

sudo poetry run py_burn     # interactive menu (needs root for USB ops)
```

### Docker (optional)

If you prefer a container over a local venv:

```bash
./build-docker.sh           # builds pyburn:latest
```

The image bundles Python dependencies **and** the system tools pyburn shells out to (`gdisk`, `wimlib`, `rsync`, etc.). Burning a real USB stick from Docker still requires passing through host devices — see the script output for the full `docker run` example.

**What that implies:** Docker is for packaging and reproducible environments, not a magic bypass around `sudo` and physical USB access.

### Project layout (max depth: 4)

```text
py_burn/
├── pyburn.py           # launcher script
├── pyproject.toml      # Poetry project config
├── poetry.lock         # locked dependency versions
├── poetry.toml         # Poetry settings (in-project venv)
├── requirements.txt    # pip pin list (Docker / CI)
├── Dockerfile          # container image definition
├── build-docker.sh     # builds the Docker image
├── .gitignore
├── LICENSE
├── README.md
├── .venv/              # local Python environment (created by poetry install)
├── py_burn/            # application package
│   ├── __main__.py
│   ├── model/
│   ├── view/
│   ├── controller/
│   └── data/
└── tests/
```

---

## 💾 Format a USB drive for storage (CLI menu)

**Use case:** blank thumb drive for files — not a bootable installer.

```bash
sudo poetry run py_burn
```

1. **Burn Settings** → set **Job mode** to `storage_only`
2. **USB Device** → pick your drive from the list (or type `/dev/sdX`)
3. **Confirm** → set safety confirmation to `yes`
4. Main menu → **Format empty storage** → read the warning → confirm

You get a single empty **FAT32** partition. No ISO. No bootloader drama. Just storage.

---

## 💿 Create a bootable Linux or Windows USB

**Use case:** install Ubuntu, Arch, Fedora, Windows 10/11, or any supported ISO.

### Step 1 — Prepare (CLI)

```bash
poetry run py_burn -check-deps
poetry run py_burn -list-usb
poetry run py_burn -download ubuntu   # optional — built-in catalog
```

Downloads land in `~/Downloads/py_burn/` by default.

### Step 2 — Burn (CLI menu)

```bash
sudo poetry run py_burn
```

1. **ISO Image** → select or enter the path to your `.iso` file (settings auto-update)
2. **USB Device** → choose the target drive
3. **Confirm** → set safety confirmation to `yes`
4. Main menu → **Burn ISO to USB** → confirm the warning

A live progress bar shows percentage, elapsed time, and copy status.

### What happens behind the scenes

```text
ISO  →  validate  →  wipe USB  →  partition  →  FAT32  →  copy files  →  verify boot files
```

Windows images get **WIM splitting** when files exceed FAT32 size limits. Linux live ISOs copy straight through. You get the boring reliability without the boring terminal archaeology.

---

## 📚 How ISO burning works

Before you flash a stick, it helps to know what you are actually making. This is the stuff Rufus never explains.

### What is an ISO file?

An **ISO** is a single file that contains a byte-for-byte snapshot of an optical disc (CD/DVD). Think of it as a `.zip` of a whole disk layout — bootloader, file system, directories, and all — frozen in time.

When you **burn** (write) an ISO to a USB drive, you are not melting anything. You are:

1. **Erasing** the USB's old partition table and data
2. **Creating** a new partition layout the firmware can boot from
3. **Formatting** that partition with a filesystem the bootloader understands
4. **Copying** the ISO's contents onto the USB so the PC can start from it

```text
┌─────────────┐     burn      ┌──────────────────────────────┐
│  image.iso  │  ──────────►  │  USB drive (bootable media)  │
│  (one file) │               │  partition + files + boot code │
└─────────────┘               └──────────────────────────────┘
```

After a successful burn, the USB is **boot media first**, not a normal folder you drag files into. Your desktop may not mount it the way you expect — that is normal.

### What the flash drive becomes

| Before burning | After burning |
|---|---|
| Empty storage or random files | A **bootable volume** with installer or live OS files |
| One FAT32/exFAT partition for documents | Often a **FAT32** system partition + boot entries |
| Safe to unplug anytime | Still removable, but now meant for **firmware boot** |

When you power on a PC and select the USB from the boot menu, the firmware reads a **bootloader** from the drive (e.g. `bootx64.efi` on UEFI systems, or legacy `bootmgr` on older BIOS setups). That bootloader then loads the operating environment stored on the stick.

pyburn prepares the partition table (**GPT** for modern UEFI, **MBR** for older hardware), formats as **FAT32** (the lingua franca of USB boot), and copies the ISO payload — including splitting oversized Windows `install.wim` files when needed.

### Install media vs live media — know the difference

Not every ISO wants the same thing from your USB. Broadly, there are three camps:

#### 1. Installer ISOs (install onto disk)

**Examples:** Windows 10/11, Ubuntu Desktop installer, Fedora Workstation, Debian netinst

**What they do:** Boot a setup environment, then **copy the OS onto your internal SSD/HDD**. The USB is a delivery truck — the OS lives on your computer after installation.

**What the USB becomes:** A reusable (or disposable) **installation stick**. You can run setup many times on different machines.

```text
USB boots  →  installer loads  →  you pick a disk  →  OS installed on internal drive
```

#### 2. Live ISOs (run from the USB)

**Examples:** Ubuntu "Try Ubuntu", Fedora Live, many rescue discs

**What they do:** Load a full desktop or shell **into RAM** (and sometimes read-only from the USB). Nothing is installed unless you click "Install". Reboot without installing and your internal disk is unchanged.

**What the USB becomes:** A **portable OS session**. Handy for testing hardware, demos, or recovery.

```text
USB boots  →  live environment runs  →  optional: install to disk
```

#### 3. Persistent live systems (the OS lives on the stick)

**Examples:** **Tails**, persistent Ubuntu Live, Kali with persistence

**What they do:** Boot **from the USB every time** and optionally **save settings, files, and browser state back to the stick** (encrypted persistence partition). The flash drive *is* the computer's disk for that session.

**What the USB becomes:** A **complete portable operating system** — not just an installer, not just a one-off live demo. Tails is designed to leave no trace on the host machine; your session lives on (and is wiped from) the USB.

```text
USB boots  →  OS runs from USB  →  changes may persist on USB  →  host disk untouched
```

| Type | Runs from USB? | Installs to PC? | Typical use |
|---|---|---|---|
| **Installer** (Windows, Ubuntu installer) | Setup environment only | Yes — that is the point | Fresh OS install |
| **Live** (Try Ubuntu) | Yes, in RAM | Optional | Test before installing |
| **Persistent live** (Tails) | Yes, ongoing | No (by design) | Privacy, portability, recovery |

### Filesystems — why FAT32 shows up everywhere

USB boot is a compatibility game. Your PC's firmware is picky about what it can read **before** any full OS driver stack is loaded.

| Filesystem | Max file size | Boot firmware support | Common role on USB |
|---|---|---|---|
| **FAT32** (vfat) | 4 GB per file | Excellent (UEFI + legacy) | Boot partitions, EFI files, small installers |
| **NTFS** | Very large | UEFI (with drivers) | Windows data, some large images |
| **ext4** | Very large | Poor pre-boot | Linux root — not ideal for EFI boot alone |

That is why pyburn formats boot partitions as **FAT32**: almost every machine can read it at power-on. Windows install images often ship a single `install.wim` larger than 4 GB, which is why pyburn can **split** it into `.swm` chunks that still fit FAT32 rules.

**Partition tables** matter too:

- **GPT** — modern standard, required for UEFI on most PCs, supports large drives
- **MBR** — older layout, still needed for some legacy BIOS-only machines

### Storage mode vs boot mode — two different animals

pyburn handles both, and they are not interchangeable:

| Mode | How to run | USB after completion |
|---|---|---|
| **Storage format** | `sudo poetry run py_burn` → job mode `storage_only` | Empty FAT32 thumb drive |
| **ISO burn** (default) | `sudo poetry run py_burn` → select ISO + device | Bootable installer or live OS |

Formatting for storage gives you drag-and-drop convenience. Burning an ISO gives you something the **boot menu** understands. Pick the job first, then the tool.

### Quick decision guide

- **"I want a blank USB for photos and documents"** → `sudo poetry run py_burn`, set job mode to `storage_only`
- **"I want to install Windows or Linux on this laptop"** → `sudo poetry run py_burn`, select an installer ISO
- **"I want to try Linux without touching my disk"** → burn a **live ISO**
- **"I want an OS that runs from the stick, like Tails"** → burn a **persistent live** image

---

## 🏗️ Architecture

Clean **MVC** — easy to read, easy to contribute:

```text
py_burn/
├── py_burn/         # application package
│   ├── model/       # usb, iso, copy, burn, deps, workflow
│   ├── view/        # Rich CLI rendering
│   ├── controller/  # CLI app + menu controller
│   └── data/        # iso_catalog.json, presets.json
├── tests/
├── pyburn.py        # launcher script
├── pyproject.toml
└── .venv/           # local Python environment (poetry)
```

```mermaid
flowchart LR
    User --> Controller
    Controller --> View
    Controller --> Model
    Model --> USB[UsbManager]
    Model --> ISO[IsoValidator]
    Model --> Copy[FileOperator]
```

- **Model** — business logic, subprocess calls, zero UI imports
- **View** — Rich panels, progress bars, figlet banners
- **Controller** — menu navigation, ISO/USB selection, burn/format jobs

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| **OS** | Linux (x86_64 recommended) |
| **Python** | 3.14+ |
| **Privileges** | `sudo` for wipe / partition / format |
| **USB** | Removable drive (8 GB+ for Windows ISOs) |
| **Tools** | `gdisk`, `mkfs.vfat`, `rsync`, `wimlib`, `wipefs`, `partprobe` |

```bash
poetry run py_burn -check-deps   # shows what is missing on your distro
```

---

## 📦 Dependencies

pyburn splits dependencies into two layers: **Python packages** (installed by Poetry into `.venv/`) and **system tools** (provided by your distro, invoked via `subprocess`). The app cannot burn or format without both.

### Python packages (runtime)

Declared in `pyproject.toml`, pinned in `poetry.lock` and `requirements.txt`.

| Package | Version | Role in pyburn |
|---|---|---|
| **[Rich](https://github.com/Textualize/rich)** | 14.3.4 | Terminal UI — panels, tables, prompts, progress bars, and live burn status in the interactive CLI |
| **[pyfiglet](https://github.com/pwaller/pyfiglet)** | 1.0.4 | ASCII banner at CLI startup (`pyburn` title in the menu header) |
| **[TinyDB](https://github.com/msiemens/tinydb)** | 4.8.2 | Lightweight embedded document database (project dependency; `TinyLogger` persists events as JSON via stdlib) |
| **markdown-it-py** | 4.2.0 | Rich dependency — Markdown rendering support inside Rich |
| **Pygments** | 2.20.0 | Rich dependency — syntax highlighting for styled terminal output |
| **mdurl** | 0.1.2 | Rich dependency — URL utilities used by the Markdown parser |

**What this implies:** three direct dependencies, all pure Python. No compiled wheels required. Rich pulls in the Markdown/highlighting stack automatically.

### Python packages (development)

Installed with `poetry install` (dev group), not needed to run pyburn end-user.

| Package | Role |
|---|---|
| **pytest** | Unit and integration test runner (`poetry run pytest`) |
| **pytest-cov** | Optional coverage reporting during test runs |
| **ruff** | Fast linter for unused imports, style, and basic errors |

### System tools (runtime)

These are **not** pip packages. pyburn shells out to them for disk operations. Your distro must provide them — `poetry run py_burn -check-deps` audits your system.

| Tool | Role in pyburn |
|---|---|
| **`lsblk`** | Detect removable USB block devices and their size |
| **`sgdisk` / `gdisk`** | Create GPT/MBR partition tables on the target drive |
| **`mkfs.vfat`** | Format the USB partition as FAT32 (boot-compatible) |
| **`wipefs`** | Clear old filesystem signatures before repartitioning |
| **`dd`** | Zero the first sectors during device wipe |
| **`partprobe`** | Refresh the kernel partition table after changes |
| **`mount` / `umount`** | Mount ISO images and USB partitions for file copy |
| **`rsync`** | Bulk-copy ISO contents to the USB with progress output |
| **`isoinfo`** | Validate ISO 9660 structure before burning |
| **`file`** | Confirm the image file is a valid ISO filesystem |
| **`wimlib-imagex`** | Verify Windows `install.wim` / `install.esd` integrity |
| **`wimsplit`** | Split oversized Windows install images for FAT32 (`.swm` chunks) |
| **`sync`** | Flush buffered writes before unmounting |

**What this implies:** pyburn orchestrates existing Linux utilities rather than reimplementing low-level disk I/O in Python. That keeps the codebase small and auditable, but means **you must install the system packages** for your distro (Arch, Debian, Fedora, etc.) — Poetry does not install them for you.

```bash
poetry run py_burn -check-deps   # list missing tools + install command for your distro
```

---

## 🖥️ CLI reference

All flags require a leading `-` (e.g. `-list-usb`, not `list-usb`).

```bash
poetry run py_burn -h                 # Help
poetry run py_burn -version            # Version
poetry run py_burn -check-deps         # Audit system tools
poetry run py_burn -list-usb           # List removable disks
poetry run py_burn -status             # Deps + device summary
poetry run py_burn -download arch       # Download ISO from catalog
sudo poetry run py_burn                # Interactive menu (burn / format)
```

After `poetry install`, you can also run `py_burn` or `pyburn` directly inside the activated `.venv`.

**Catalog examples:** `arch`, `ubuntu`, `fedora`, `debian` — full list in `py_burn/data/iso_catalog.json`.

---

## ⚠️ Safety

> **Everything on the target USB will be erased. Forever. Like, actually gone.**

- Unplug drives you are **not** flashing
- Run `poetry run py_burn -list-usb` and triple-check `/dev/sdX`
- The CLI menu blocks burn/format until required fields are complete and you confirm `yes`

---

## 🌐 Open Source & MIT License

pyburn is **100% open source** under the [**MIT License**](LICENSE).

That means you can:

- ✅ Use it commercially
- ✅ Modify and redistribute it
- ✅ Fork it for your own distro or workflow
- ✅ Learn from the code without legal headaches

```text
Copyright (c) 2025 tuliofh01
Permission is hereby granted, free of charge, to any person obtaining a copy...
```

**Want to contribute?**

```bash
poetry install
poetry run pytest
poetry run ruff check py_burn tests
```

- Business logic → `model/`
- CLI rendering → `view/`
- User flows → `controller/`
- Tests → `tests/`

Pull requests welcome. Found a bug? Open an issue. Made it better? You are a legend.

---

## ❓ FAQ

<details>
<summary><strong>Is pyburn a Rufus alternative for Linux?</strong></summary>

Yes. pyburn covers the same core jobs — formatting USB drives and writing bootable ISO images — natively on Linux, without Wine or a Windows VM.
</details>

<details>
<summary><strong>Can I format a USB to FAT32 without burning an ISO?</strong></summary>

Yes. Use <code>sudo poetry run py_burn</code>, set job mode to <code>storage_only</code>, then run the format job from the menu.
</details>

<details>
<summary><strong>Does pyburn support Windows 10 and Windows 11 ISOs?</strong></summary>

Yes. The copy pipeline handles large Windows install images, including WIM splitting for FAT32 constraints.
</details>

<details>
<summary><strong>Which Linux distros are supported?</strong></summary>

Arch, Debian/Ubuntu, Fedora/RHEL, and openSUSE families are detected for dependency reporting. The app itself runs anywhere you have Python 3.14+ and the required system tools.
</details>

<details>
<summary><strong>What is the difference between a live USB and an installer USB?</strong></summary>

A <strong>live USB</strong> runs the operating system from the stick (often into RAM) so you can try it without installing. An <strong>installer USB</strong> boots a setup wizard whose goal is to copy the OS onto your internal drive. Tails is a special case: a <strong>persistent live</strong> system designed to run from the USB itself, not to install onto your PC. See <a href="#-how-iso-burning-works">How ISO burning works</a> for the full breakdown.
</details>

<details>
<summary><strong>Why does <code>sudo poetry run py_burn</code> print help instead of the menu?</strong></summary>

It should open the interactive menu. If you see help text, you may be on an older build where empty args mapped to <code>-h</code>. Update the project and run again with no extra flags. Use <code>poetry run py_burn -h</code> only when you want help.
</details>

<details>
<summary><strong>Is pyburn really free?</strong></summary>

Yes. MIT licensed, open source, no paywall, no telemetry required. Clone it and own it.
</details>

---

## 📄 License

Released under the [MIT License](LICENSE).

---

<p align="center">
  <strong>pyburn</strong> — open source · MIT · built with Python, Rich, and figlet<br>
  <sub>Stop rebooting into Windows just to flash a stick. 🔥</sub>
</p>
