from __future__ import annotations

import sys

from py_burn.controller.app import PyBurnCLI


def main() -> None:
    cli = PyBurnCLI()
    sys.exit(cli.run(sys.argv[1:]))


if __name__ == "__main__":
    main()
