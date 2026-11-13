"""Build the Python backend as a single executable for the Tauri bundle.

Usage (from the repository root):

    uv run --with pyinstaller python scripts/build_sidecar.py

Writes desktop/src-tauri/binaries/anime-studio-core-<target-triple>[.exe],
the name Tauri's `externalBin` expects for the current platform.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARIES = ROOT / "desktop" / "src-tauri" / "binaries"


def target_triple() -> str:
    output = subprocess.run(
        ["rustc", "-vV"], capture_output=True, text=True, check=True
    ).stdout
    for line in output.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit("could not read the Rust host triple from `rustc -vV`")


def main() -> None:
    build = ROOT / "build" / "sidecar"
    entry = build / "entry.py"
    build.mkdir(parents=True, exist_ok=True)
    entry.write_text("from src.sidecar.__main__ import main\n\nmain()\n", encoding="utf-8")
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", str(entry),
            "--onefile", "--noconfirm", "--clean",
            "--name", "anime-studio-core",
            "--paths", str(ROOT),
            "--collect-submodules", "src",
            # The desktop backend never loads the old Qt GUI.
            "--exclude-module", "src.gui",
            "--exclude-module", "PySide6",
            "--exclude-module", "shiboken6",
            "--exclude-module", "qasync",
            "--exclude-module", "qdarktheme",
            "--distpath", str(build / "dist"),
            "--workpath", str(build / "work"),
            "--specpath", str(build),
        ],
        check=True,
    )  # fmt: skip
    suffix = ".exe" if sys.platform == "win32" else ""
    built = build / "dist" / f"anime-studio-core{suffix}"
    BINARIES.mkdir(parents=True, exist_ok=True)
    target = BINARIES / f"anime-studio-core-{target_triple()}{suffix}"
    shutil.copy2(built, target)
    print(f"sidecar ready: {target}")


if __name__ == "__main__":
    main()
