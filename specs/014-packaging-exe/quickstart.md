# Quickstart: Building & Running Standalone Anime Studio (.exe)

This guide explains how to build the standalone Windows executable and package portable external tools.

---

## 1. Building the Executable

Run the automated packaging script using `uv`:

```powershell
uv run python scripts/build_exe.py --clean
```

This will:
1. Clean previous build artifacts (`build/` and `dist/`).
2. Run PyInstaller with `AnimeStudio.spec`.
3. Collect all PySide6 binaries, Qt plugins, themes, fontTools, and project modules.
4. Create the portable `tools/` folder structure inside `dist/AnimeStudio/`.
5. Execute an automated smoke test (`dist/AnimeStudio/AnimeStudio.exe --smoke-test`) to verify binary integrity.

---

## 2. Debugging Builds

If you need to diagnose startup issues or see console log output in real time, build with `--debug-console`:

```powershell
uv run python scripts/build_exe.py --debug-console
```

This attaches a Windows console window to `AnimeStudio.exe` while keeping the PySide6 GUI window running.

---

## 3. Bundling Portable External Tools (Optional)

Anime Studio automatically checks for external tools inside `dist/AnimeStudio/tools/`:

```text
dist/AnimeStudio/
├── AnimeStudio.exe
├── tools/
│   ├── ffmpeg.exe
│   ├── mkvmerge.exe
│   ├── mkvextract.exe
│   └── alass.bat
└── ... (Qt DLLs and assets)
```

If these tools are placed in `tools/`, Anime Studio will use them directly without requiring system-wide installation (Scoop or Program Files).

---

## 4. Distributing the Package

Simply zip the entire `dist/AnimeStudio/` directory:

```powershell
Compress-Archive -Path dist\AnimeStudio\* -DestinationPath AnimeStudio-v3.0.0-win64.zip
```

Users can extract the ZIP anywhere on their Windows machine and launch `AnimeStudio.exe` with zero installation required!
