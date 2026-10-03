"""Automated build and verification script for packaging Anime Studio v3 into a Windows .exe.

Usage:
    uv run python scripts/build_exe.py [--clean] [--debug-console] [--smoke-test]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def get_dir_size_mb(path: Path) -> float:
    """Calculate the total size of a directory in megabytes."""
    total_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total_bytes / (1024 * 1024)


def create_tools_readme(tools_dir: Path) -> None:
    """Create README.txt inside the tools/ folder explaining portable binaries."""
    tools_dir.mkdir(parents=True, exist_ok=True)
    readme_path = tools_dir / "README.txt"
    readme_path.write_text(
        "Anime Studio Portable Tools Directory\n"
        "======================================\n\n"
        "You can place portable external tools directly in this directory or its subfolders:\n"
        "- ffmpeg.exe\n"
        "- mkvmerge.exe\n"
        "- mkvextract.exe\n"
        "- alass.bat / alass.exe\n"
        "- ots-sanitize.exe\n\n"
        "Anime Studio automatically scans this folder upon startup before checking system PATH.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Anime Studio standalone executable."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove build/ and dist/ folders before building.",
    )
    parser.add_argument(
        "--debug-console",
        action="store_true",
        help="Build with an attached console window for debugging.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        default=True,
        help="Run an automated verification of the compiled binary after build.",
    )
    parser.add_argument(
        "--no-smoke-test",
        action="store_false",
        dest="smoke_test",
        help="Skip post-build verification.",
    )

    args = parser.parse_args()
    repo_root = Path.cwd().resolve()
    spec_file = repo_root / "AnimeStudio.spec"

    if not spec_file.is_file():
        print(f"Error: spec file not found at {spec_file}", file=sys.stderr)
        return 1

    print("==================================================")
    print("   Anime Studio v3 - Windows Packaging Pipeline   ")
    print("==================================================")
    print(f"Repository Root: {repo_root}")
    print(f"Specification:   {spec_file.name}")
    print(f"Debug Console:   {args.debug_console}")
    print(f"Smoke Test:      {args.smoke_test}")
    print("--------------------------------------------------")

    build_dir = repo_root / "build"
    dist_dir = repo_root / "dist"

    if args.clean:
        print("Cleaning previous build artifacts...")
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)
        if dist_dir.exists():
            shutil.rmtree(dist_dir, ignore_errors=True)

    env = os.environ.copy()
    if args.debug_console:
        env["ANIME_STUDIO_DEBUG_CONSOLE"] = "1"
    else:
        env["ANIME_STUDIO_DEBUG_CONSOLE"] = "0"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_file),
        "--noconfirm",
    ]

    print(f"Running command: {' '.join(cmd)}")
    start_time = time.perf_counter()

    result = subprocess.run(cmd, cwd=str(repo_root), env=env)
    if result.returncode != 0:
        print(
            f"\n[FAIL] PyInstaller exited with code {result.returncode}",
            file=sys.stderr,
        )
        return result.returncode

    duration_s = time.perf_counter() - start_time
    output_dir = dist_dir / "AnimeStudio"
    output_exe = output_dir / "AnimeStudio.exe"

    if not output_exe.is_file():
        print(f"\n[FAIL] Target executable not found at {output_exe}", file=sys.stderr)
        return 1

    # Create tools/ folder inside output distribution
    tools_dir = output_dir / "tools"
    create_tools_readme(tools_dir)

    size_mb = get_dir_size_mb(output_dir)
    print("\n--------------------------------------------------")
    print("Build Succeeded!")
    print(f"Output Location: {output_exe}")
    print(f"Distribution:    {size_mb:.1f} MB")
    print(f"Build Time:      {duration_s:.1f}s")
    print("--------------------------------------------------")

    if args.smoke_test:
        print("\nExecuting post-build smoke test on AnimeStudio.exe...")
        try:
            smoke_run = subprocess.run(
                [str(output_exe), "--smoke-test"],
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            print(f"Smoke test output: {smoke_run.stdout.strip()}")
            if (
                smoke_run.returncode == 0
                and "Anime Studio smoke test: OK" in smoke_run.stdout
            ):
                print("[PASS] Smoke test verified: binary loaded and executed cleanly!")
            else:
                print(
                    f"[FAIL] Smoke test failed with returncode {smoke_run.returncode}",
                    file=sys.stderr,
                )
                if smoke_run.stderr:
                    print(f"Stderr: {smoke_run.stderr}", file=sys.stderr)
                return 1
        except subprocess.TimeoutExpired:
            print("[FAIL] Smoke test timed out after 30 seconds!", file=sys.stderr)
            return 1

    print("\nPackage is ready for distribution!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
