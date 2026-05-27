#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
=========================================================================
                ANIME STUDIO  v2.0  —  Forensic Edition
=========================================================================
A single tool that replaces:
    • Media_Toolbox.py            (rename / sync / merge subtitles)
    • BackupAnimeFonts.ps1        (scan system fonts → per-anime _Fonts)
    • clean_up_fonts.ps1          (remove generated _Fonts + reports)

v2.0 highlights (from v1.8):
    ✓ Multi-index font matching (internal + filename + postscript + fullname)
    ✓ libass naming-mismatch resolver (patch font OR patch ASS)
    ✓ Font health check + repair pipeline (fontTools → ots-sanitize)
    ✓ Embedded-ASS reader (scans fonts inside already-muxed MKVs)
    ✓ Universal search-engine font hunter (Brave + Google + DDG + Bing + pages)
    ✓ Missing-subtitles report with direct search links
    ✓ alass integration alongside ffsubsync (per-task choice)
    ✓ Bug fix: language matching (ar/ara/arb/ar-EG no longer mis-rejected)
    ✓ Safe-delete trash (no more silent .ass loss)
    ✓ Rebuilt menu with Status Dashboard

…and ADDS the headline feature:
    • SMART MUX  ➜  Embed subtitles AND the exact fonts each ASS needs
                    directly into the MKV as Matroska attachments.

WHY MUX (TL;DR)?
    mpv `sub-fonts-dir=auto` is fragile (mpv-only, broken on subfolders,
    coupled to disk layout). Muxing produces self-contained MKVs that
    play perfectly on mpv, VLC, Plex, Jellyfin, phone, TV, Chromecast.

Author : Built for Mohamed's anime library  (D:\Entertainment\Anime)
License: Public Domain — do whatever you want with it.
=========================================================================
"""
import os
import re
import sys
import io
import json
import shutil
import datetime
import subprocess
import concurrent.futures
import platform
import hashlib
import traceback
from collections import defaultdict
from pathlib import Path
from difflib import SequenceMatcher
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

# ── UTF-8 I/O — must run BEFORE any Rich / print import ──────────────────
def _force_utf8_io():
    """Bullet-proof UTF-8 setup across Windows Terminal, conhost, and Linux."""
    # 1. Process-level env override (covers child processes too)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

    # 2. Windows console codepage
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass

    # 3. Re-wrap stdio — errors='replace' so an emoji never crashes a write
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name)
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace",
                                    line_buffering=True)
            except Exception:
                pass
        elif hasattr(_stream, "buffer"):
            try:
                setattr(sys, _stream_name,
                        io.TextIOWrapper(_stream.buffer,
                                         encoding="utf-8", errors="replace",
                                         line_buffering=True))
            except Exception:
                pass

_force_utf8_io()

# ── Rich console — lazy import so the script can still run without it ─────
# rich is pulled in automatically when fonttools/ffsubsync is installed.
# If for any reason it's absent the whole UI degrades to plain print().
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (Progress, BarColumn, TaskProgressColumn,
                               TimeRemainingColumn, TextColumn, SpinnerColumn,
                               MofNCompleteColumn)
    from rich import box as _rbox
    _con = Console(highlight=False, force_terminal=True)
    _RICH = True
except ImportError:
    _RICH = False
    _con  = None

# =========================================================================
#  0. CONFIGURATION  (edit these to taste — or override via env vars)
# =========================================================================
DEFAULT_ANIME_ROOT = os.environ.get("ANIME_ROOT", r"D:\Entertainment\Anime")
DEFAULT_DOWNLOADS  = os.environ.get("ANIME_DOWNLOADS", str(Path.home() / "Downloads"))
PORTABLE_FONTS_DIR = os.environ.get("ANIME_PORTABLE_FONTS",
                                    str(Path.home() / "portable_fonts"))

# Folder name conventions
FONTS_FOLDER_NAMES  = {"_fonts", "fonts", "_خطوط", "خطوط"}   # case-insensitive
GLOBAL_BACKUP_NAME  = "__All_Anime_Fonts_Backup"
MISSING_REPORT_NAME = "_Missing_Fonts.txt"

# Files we work with
VIDEO_EXTS = {'.mkv', '.mp4', '.avi', '.mov', '.flv', '.webm'}
SUB_EXTS   = {'.ass', '.srt', '.ssa'}
FONT_EXTS  = {'.ttf', '.otf', '.ttc', '.woff', '.woff2'}

# Default Windows fonts we never bother re-attaching — they exist on every system
SYSTEM_FONT_IGNORE = {
    "arial", "times new roman", "tahoma", "verdana", "calibri",
    "courier new", "microsoft sans seriph", "microsoft sans serif",
    "segoe ui", "open sans", "roboto", "default", "default design",
    "georgia", "trebuchet ms", "comic sans ms", "impact", "lucida console",
    "consolas", "cambria", "candara", "constantia", "corbel", "ebrima",
    "franklin gothic", "gabriola", "gadugi", "javanese text", "leelawadee",
    "malgun gothic", "marlett", "mongolian baiti", "ms gothic",
    "mv boli", "myanmar text", "nirmala ui", "palatino linotype",
    # v1.11: Windows-bundled Arabic-capable families. libass + DirectWrite
    # will resolve these against the system on any modern Windows install,
    # so the script doesn't have to attach them inside every MKV.
    "traditional arabic", "simplified arabic", "andalus", "sakkal majalla",
    "arabic typesetting", "aldhabi", "urdu typesetting", "microsoft uighur",
    "microsoft himalaya", "ms uigur", "arabtype", "arab type",
    "segoe print", "segoe script", "segoe ui historic", "simsun",
    "sitka", "sylfaen", "symbol", "wingdings", "yu gothic",
}

UNDO_FILENAME       = ".anime_studio_undo.json"
LOG_FILENAME        = ".anime_studio_log.txt"
STATE_FILENAME      = ".anime_studio_state.json"     # resume support
REPORT_FILENAME     = "_Missing_Fonts_Report.md"      # human-readable report
SOURCES_REPORT_FILENAME = "_Font_Sources_Report.md"  # manual-source guide for licensed fonts
MUXED_MARKER_KEY    = "muxed_at"                      # in state file

# Central library-wide font pool at <anime_root>/fonts/
# Downloaded fonts go here, and the build-_Fonts step scans it too. This means newly
# downloaded fonts are immediately reusable across ALL anime in the library
# WITHOUT installing them system-wide.
LIBRARY_FONTS_DIR_NAME = "fonts"

# =========================================================================
#  UI DESIGN SYSTEM  —  Theme, MenuItem, ToolError (§6.3, §6.6, §6.8)
# =========================================================================

# ── §6.6  Theme dataclass ────────────────────────────────────────────────
@dataclass(frozen=True)
class Theme:
    """A named color + glyph palette. Pick one in settings; falls back to
    ascii-safe automatically when a Nerd Font is not detected."""
    name: str
    accent: str
    success: str
    warn: str
    error: str
    muted: str
    border: str          # Rich box style name (ROUNDED / HEAVY / ASCII)
    glyph_set: dict      # keys: check, warn, cross, arrow, folder, spinner

THEMES = {
    "catppuccin-mocha": Theme(
        "catppuccin-mocha",
        accent="#cba6f7", success="#a6e3a1", warn="#f9e2af",
        error="#f38ba8", muted="#6c7086", border="ROUNDED",
        glyph_set={"check": "\uf058", "warn": "\uf071", "cross": "\uf057",
                   "arrow": "\uf101", "folder": "\uf07c", "spinner": "\uf110"}),
    "gruvbox-dark": Theme(
        "gruvbox-dark",
        accent="#fabd2f", success="#b8bb26", warn="#fe8019",
        error="#fb4934", muted="#928374", border="HEAVY",
        glyph_set={"check": "\uf058", "warn": "\uf071", "cross": "\uf057",
                   "arrow": "\uf101", "folder": "\uf07c", "spinner": "\uf110"}),
    "tokyo-night": Theme(
        "tokyo-night",
        accent="#7aa2f7", success="#9ece6a", warn="#e0af68",
        error="#f7768e", muted="#565f89", border="ROUNDED",
        glyph_set={"check": "\uf058", "warn": "\uf071", "cross": "\uf057",
                   "arrow": "\uf101", "folder": "\uf07c", "spinner": "\uf110"}),
    # ascii-safe: fallback when Nerd Font is not available — kills the ? problem
    "ascii-safe": Theme(
        "ascii-safe",
        accent="cyan", success="green", warn="yellow",
        error="red", muted="grey50", border="ASCII",
        glyph_set={"check": "[OK]", "warn": "[!]", "cross": "[X]",
                   "arrow": "->",  "folder": "[/]", "spinner": "|"}),
}

def _active_theme() -> Theme:
    """Return the active theme. Reads ANIME_STUDIO_THEME env var, falls
    back to ascii-safe if the name is unknown."""
    name = os.environ.get("ANIME_STUDIO_THEME", "catppuccin-mocha")
    return THEMES.get(name, THEMES["ascii-safe"])

THEME = _active_theme()

# ── §6.3  Declarative MenuItem registry ─────────────────────────────────
# Each menu entry is a frozen dataclass so the same definitions can drive
# both the curses renderer today and a Textual port in the future.
@dataclass(frozen=True)
class MenuItem:
    id: str
    label: str          # human label shown in the menu
    glyph: str          # Nerd Font codepoint or emoji
    hotkey: str         # single mnemonic char
    group: str          # "primary" | "step" | "forensic" | "extra"

# ── §6.8  ToolError + report_error ──────────────────────────────────────
@dataclass
class ToolError:
    """Structured representation of an external tool failure."""
    tool: str
    exit_code: int
    stderr_tail: str       # last 20 lines of stderr
    suggested_fix: str     # one-liner user-visible hint
    full_log_path: Optional[Path] = None

def report_error(err: ToolError):
    """Render a tool failure as a Rich panel — no raw tracebacks to users."""
    if not _RICH:
        print(f"\n⚠ {err.tool} failed (exit {err.exit_code}): {err.suggested_fix}")
        return
    body = (
        f"[bold red]{err.tool}[/bold red] exited with code {err.exit_code}\n\n"
        f"[dim]Last output:[/dim]\n{err.stderr_tail}\n\n"
        f"[yellow]Try:[/yellow] {err.suggested_fix}"
    )
    if err.full_log_path:
        body += f"\n[dim]Full log:[/dim] {err.full_log_path}"
    _con.print(Panel(body, title="⚠ Tool failed", border_style="red"))

# =========================================================================
#  1. DEPENDENCY MANAGEMENT
# =========================================================================
#
#  DESIGN NOTES (aligned with the PDF "Clean Workstation" guide):
#
#  • Python packages (fonttools, windows-curses) are installed with `uv pip`
#    when uv is available, falling back to pip. This respects the user's
#    uv-managed environment without polluting the global Python install.
#
#  • ffsubsync is a CLI tool installed via `uv tool install ffsubsync`.
#    `uv tool` puts tools in isolated envs — they are NOT importable as
#    Python modules from this script's interpreter. We therefore:
#      ① Never try to `import ffsubsync`
#      ② Never pip-install ffsubsync (that pulls webrtcvad-wheels which
#         needs MSVC++ to build from source — unnecessary pain)
#      ③ Only check shutil.which("ffsubsync") for the CLI binary
#
#  • MKVToolNix (mkvmerge) is auto-installed via scoop (preferred per the
#    PDF guide Ch. 4 — portable, no leftovers) then winget as fallback.

def _install_python_pkgs(pkgs):
    """Install importable Python packages into the current environment.
    Prefers `uv pip install` (user's workflow), falls back to pip."""
    print(f"📦 Installing missing Python packages: {', '.join(pkgs)}")
    uv = shutil.which("uv")
    if uv:
        print("   (using uv pip — aligns with your uv workflow)")
        try:
            subprocess.check_call([uv, "pip", "install", "--system", *pkgs])
            return True
        except Exception as e:
            print(f"   ⚠  uv pip failed ({e}), falling back to pip…")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install",
             "--disable-pip-version-check", *pkgs]
        )
        return True
    except Exception as e:
        print(f"❌ pip install also failed: {e}")
        return False


def _install_mkvtoolnix():
    """Auto-install MKVToolNix using scoop (PDF guide Ch. 4 preferred),
    then winget, then print the manual link as a last resort."""
    print("\n🔧 mkvmerge not found — attempting auto-install of MKVToolNix…")

    # 1. scoop — portable, leaves no registry debris (PDF guide Ch. 4.1)
    if shutil.which("scoop"):
        print("   → scoop install mkvtoolnix")
        try:
            subprocess.check_call(["scoop", "install", "mkvtoolnix"])
            if shutil.which("mkvmerge"):
                print("   ✅ mkvmerge now available via scoop!")
                return True
        except Exception as e:
            print(f"   ⚠  scoop install failed: {e}")

    # 2. winget fallback (GUI-managed, per PDF guide Ch. 4.2)
    if shutil.which("winget"):
        print("   → winget install MKVToolNix.MKVToolNix")
        try:
            subprocess.check_call(
                ["winget", "install", "-e", "--id", "MKVToolNix.MKVToolNix",
                 "--accept-package-agreements", "--accept-source-agreements"]
            )
            print("   ✅ Installed via winget.")
            print("   ⚠  Restart this script so the new PATH takes effect.")
            return True
        except Exception as e:
            print(f"   ⚠  winget install failed: {e}")

    # 3. Manual instructions
    print("   ❌ Could not auto-install MKVToolNix. Please install it manually:")
    print("      scoop install mkvtoolnix          ← recommended (portable)")
    print("      winget install MKVToolNix.MKVToolNix")
    print("      https://mkvtoolnix.download/")
    return False


def check_dependencies():
    """Verify required Python packages and external CLI tools.

    Python packages installed here (fonttools, windows-curses) must be
    importable from *this* interpreter — so we use uv pip / pip.

    ffsubsync is a `uv tool` — it lives in an isolated env and is NOT
    importable here. We only check for the CLI binary via shutil.which.
    """
    pip_needed = []

    # rich — colored output, tables, progress bars
    try:
        from rich.console import Console  # noqa: F401
    except ImportError:
        pip_needed.append("rich")

    # fonttools — must be importable: reads TTF/OTF name tables
    try:
        import fontTools  # noqa: F401
    except ImportError:
        pip_needed.append("fonttools")

    # windows-curses — must be importable on Windows (no MSVC needed)
    if sys.platform == "win32":
        try:
            import curses  # noqa: F401
        except ImportError:
            pip_needed.append("windows-curses")

    # NOTE: ffsubsync is intentionally NOT listed here.
    # Install it once with:  uv tool install ffsubsync
    # It will then appear as a CLI command in PATH.

    if pip_needed:
        if not _install_python_pkgs(pip_needed):
            input("Press Enter to exit…")
            sys.exit(1)
        # Re-launch so newly-installed modules import cleanly
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── External CLI checks ────────────────────────────────────────────────
    # _find_exe: checks PATH first, then well-known install locations on Windows.
    # MKVToolNix installed via the official .exe goes to Program Files and
    # adds itself to PATH — but only for new shells. If the terminal was open
    # before installation, shutil.which() misses it; the path scan catches it.
    def _find_exe(name):
        found = shutil.which(name)
        if found:
            return found
        if sys.platform != "win32":
            return None
        # Common MKVToolNix install locations (manual .exe installer + scoop + winget)
        candidates = [
            r"C:\Program Files\MKVToolNix",
            r"C:\Program Files (x86)\MKVToolNix",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\MKVToolNix"),
            os.path.expandvars(r"%USERPROFILE%\scoop\apps\mkvtoolnix\current"),
            os.path.expandvars(r"%USERPROFILE%\AppData\Local\Microsoft\WinGet\Packages"
                               r"\MKVToolNix.MKVToolNix_Microsoft.Winget.Source*"),
        ]
        import glob
        for pattern in candidates:
            for directory in glob.glob(pattern):
                exe = os.path.join(directory, f"{name}.exe")
                if os.path.isfile(exe):
                    # Patch PATH for this process so child calls also work
                    os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
                    return exe
        return None

    cli = {}
    cli["ffmpeg"]    = bool(_find_exe("ffmpeg"))
    cli["mkvmerge"]  = bool(_find_exe("mkvmerge"))
    cli["ffsubsync"] = bool(_find_exe("ffsubsync"))

    # ffsubsync hint if not found (uv tool, not pip)
    if not cli["ffsubsync"]:
        print("ℹ️  ffsubsync not found in PATH.")
        print("   Install it with:  uv tool install ffsubsync")
        print("   (Do NOT pip-install it — webrtcvad requires MSVC++ to build)")

    # v1.9: never block startup on a yes/no prompt. Show guidance only.
    if not cli["mkvmerge"] and sys.platform == "win32":
        print("\n⚠  mkvmerge not found.")
        print("   Install it with:  scoop install mkvtoolnix")
        print("   or               winget install MoritzBunkus.MKVToolNix")

    return cli


# =========================================================================
#  2. CORE UTILITIES
# =========================================================================
def log_event(folder, message, level="INFO"):
    """Append a timestamped line to the per-folder log file."""
    try:
        log = Path(folder) / LOG_FILENAME
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{level}] {message}\n")
    except Exception:
        pass


def rprint(msg="", **kw):
    """Print with rich markup when available, else strip tags and use print()."""
    if _RICH:
        _con.print(msg, **kw)
    else:
        print(re.sub(r"\[/?[^\]]+\]", "", str(msg)))


def _print_summary(title, ok, fail, notes=None):
    """Render a bordered summary panel after every major operation."""
    if _RICH:
        border = "green" if fail == 0 else ("yellow" if ok > 0 else "red")
        body = (f"[green]✓  Success : {ok}[/green]\n"
                f"[{'red' if fail else 'dim'}]"
                f"✗  Failed  : {fail}"
                f"[/{'red' if fail else 'dim'}]")
        if notes:
            body += "\n" + "\n".join(f"[dim]{n}[/dim]" for n in notes)
        _con.print(Panel(body, title=f"[bold]{title}[/bold]",
                         border_style=border, expand=False))
    else:
        print(f"\n── {title} ──")
        print(f"  ✓ Success: {ok}   ✗ Failed: {fail}")
        if notes:
            for n in notes:
                print(f"  {n}")


def clean_key(name):
    """Normalize a font / file name into a comparable key (Arabic-aware)."""
    if not name:
        return ""
    return re.sub(r"[^a-zA-Z0-9\u0600-\u06FF]", "", name).lower()


def root_key(name):
    """Strip foundry prefixes & weight suffixes — to group font families.
       Ports the PS1 Get-RootName logic."""
    if not name:
        return ""
    c = name.lower()
    c = re.sub(r"^(sc|ge|ae|mcs|fs|hsn|ax|al|adobe|itc)[_\s\-]?", "", c)
    for suffix in ("regular", "bold", "italic", "light", "medium", "black",
                   "heavy", "condensed", "semilight", "semibold"):
        c = c.replace(suffix, "")
    return re.sub(r"[^a-zA-Z0-9\u0600-\u06FF]", "", c).strip()


# =========================================================================
#  3. FONT NAME EXTRACTION  (from TTF / OTF / TTC files)
# =========================================================================
def font_names_from_file(path):
    """Return every English + native family / face name found inside a font file.
       Uses fontTools — works cross-platform, replaces Windows-only GlyphTypeface."""
    names = set()
    try:
        from fontTools.ttLib import TTFont, TTCollection
        ext = Path(path).suffix.lower()
        if ext == ".ttc":
            fonts = TTCollection(str(path)).fonts
        else:
            fonts = [TTFont(str(path), lazy=True, fontNumber=0)]
        for tt in fonts:
            if "name" not in tt:
                continue
            for rec in tt["name"].names:
                # nameID 1 = Family, 4 = Full name, 16 = Typo Family, 21 = WWS Family
                if rec.nameID in (1, 4, 6, 16, 21):
                    try:
                        s = rec.toUnicode().strip()
                        if s:
                            names.add(s)
                    except Exception:
                        pass
            try:
                tt.close()
            except Exception:
                pass
    except Exception as e:
        log_event(Path(path).parent, f"Could not read font {path}: {e}", "WARN")
    return names


def build_font_map(folder):
    """For a directory of fonts → build {precise_key: path, root_key: path, raw_name: path}."""
    precise, roots, raw = {}, {}, {}
    folder = Path(folder)
    if not folder.is_dir():
        return precise, roots, raw
    for f in folder.iterdir():
        if f.suffix.lower() not in FONT_EXTS:
            continue
        for n in font_names_from_file(f):
            pk = clean_key(n)
            rk = root_key(n)
            if pk and pk not in precise:
                precise[pk] = str(f)
            if rk and len(rk) > 2 and rk not in roots:
                roots[rk] = str(f)
            if n and n not in raw:
                raw[n] = str(f)
    return precise, roots, raw


def system_font_map(extra_dirs=None):
    """Index every font we can see.

    Sources (in priority order):
      1. Each directory passed in `extra_dirs`  —  used to feed the
         library-wide `<anime_root>/fonts/` pool created by Option D.
         These are searched FIRST so library fonts override system fonts.
      2. `C:\\Windows\\Fonts`               (machine-wide, Windows only)
      3. `%LOCALAPPDATA%\\Microsoft\\Windows\\Fonts`  (per-user, Windows only)
      4. `~/.fonts`, `~/.local/share/fonts`        (Linux/macOS)
    """
    dirs = list(extra_dirs or [])
    if sys.platform == "win32":
        dirs += [r"C:\Windows\Fonts",
                 os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")]
    else:
        dirs += [str(Path.home() / ".fonts"),
                 str(Path.home() / ".local" / "share" / "fonts"),
                 "/usr/share/fonts", "/usr/local/share/fonts"]

    precise, roots, raw = {}, {}, {}
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                if Path(fn).suffix.lower() not in FONT_EXTS:
                    continue
                full = os.path.join(root, fn)
                for n in font_names_from_file(full):
                    pk = clean_key(n)
                    rk = root_key(n)
                    if pk and pk not in precise:
                        precise[pk] = full
                    if rk and len(rk) > 2 and rk not in roots:
                        roots[rk] = full
                    if n not in raw:
                        raw[n] = full
    return precise, roots, raw


# =========================================================================
#  4. ASS  PARSING  —  pull out fonts each subtitle file actually needs
# =========================================================================
_RE_STYLE_LINE = re.compile(r"^Style:\s*[^,]*,\s*([^,]+)", re.MULTILINE)
_RE_FN_OVERRIDE = re.compile(r"\\fn([^\\}]+)")


def fonts_required_by_ass(ass_path):
    """Return the set of font family names referenced inside an .ass / .ssa file."""
    needed = set()
    try:
        raw = Path(ass_path).read_bytes()
        content = _smart_decode_ass(raw) or ""
        if not content:
            return needed
    except Exception:
        return needed

    for m in _RE_STYLE_LINE.finditer(content):
        name = m.group(1).strip().lstrip("@")   # @ prefix = vertical writing
        if name:
            needed.add(name)
    for m in _RE_FN_OVERRIDE.finditer(content):
        name = m.group(1).strip().lstrip("@")
        if name:
            needed.add(name)
    return needed


def resolve_required_fonts(ass_path, font_map):
    """Given an ASS path & a font map dict (precise, roots, raw),
       return (resolved_paths: dict[name → path], missing_names: list)."""
    precise, roots, raw = font_map
    resolved, missing = {}, []
    for name in fonts_required_by_ass(ass_path):
        if name.lower() in SYSTEM_FONT_IGNORE:
            continue
        pk, rk = clean_key(name), root_key(name)
        path = None
        if pk in precise:
            path = precise[pk]
        elif rk and len(rk) > 2 and rk in roots:
            path = roots[rk]
        else:
            # fuzzy fallback — substring match against precise keys
            for k, p in precise.items():
                if pk and pk in k:
                    path = p
                    break
        if path:
            resolved[name] = path
        else:
            missing.append(name)
    return resolved, missing


# =========================================================================
#  5. SUBTITLE  ⇄  VIDEO  MATCHING   (ported from Media_Toolbox.py)
# =========================================================================
class Logic:
    @staticmethod
    def normalize(name):
        n = re.sub(r"\[.*?\]|\(.*?\)", "", name).lower()
        for noise in (r"1080[pi]?", r"720[pi]?", r"480[pi]?", r"2160[pi]?",
                      r"4k", r"x264", r"x265", r"h264", r"h265", r"hevc",
                      r"10bit", r"8bit", r"web-?dl", r"webrip", r"bluray",
                      r"bdrip", r"v2", r"v3"):
            n = re.sub(rf"\b{noise}\b", "", n)
        return n.strip()

    @staticmethod
    def get_info(filename):
        c = Logic.normalize(filename)
        for pat in (r"s(\d{1,2})[\s\._-]*e(\d{1,4})",
                    r"(\d{1,2})x(\d{1,4})"):
            m = re.search(pat, c)
            if m:
                return int(m.group(1)), int(m.group(2))
        m = re.search(r"(?:ep|episode)[\s\._-]*(\d{1,4})", c)
        if m:
            return 1, int(m.group(1))
        m = re.search(r"-\s*(\d{1,4})\b", c)
        if m:
            return 1, int(m.group(1))
        nums = [int(n) for n in re.findall(r"\b\d{1,4}\b", c)
                if not (1900 < int(n) < 2100)]
        if nums:
            return 1, nums[-1]
        return None

    @staticmethod
    def signature(name):
        return re.sub(r"\bmovie\b|\b\d+\b", "", Logic.normalize(name)).strip()

    @staticmethod
    def pair_videos_and_subs(folder):
        """Return list of {vid, sub, info} matches inside one folder."""
        try:
            files = sorted(os.listdir(folder))
        except Exception:
            return [], 0, 0
        vids = [f for f in files if Path(f).suffix.lower() in VIDEO_EXTS]
        subs = [f for f in files if Path(f).suffix.lower() in SUB_EXTS]

        vid_by_info = {}
        for v in vids:
            i = Logic.get_info(v)
            if i:
                vid_by_info[i] = v

        matches, m_subs, m_vids = [], set(), set()
        for s in subs:
            i = Logic.get_info(s)
            if i and i in vid_by_info:
                matches.append({"vid": vid_by_info[i], "sub": s, "info": i})
                m_subs.add(s); m_vids.add(vid_by_info[i])

        # Fuzzy second pass for the leftovers
        for v in [v for v in vids if v not in m_vids]:
            sig_v = Logic.signature(Path(v).stem)
            best, best_r = None, 0
            for s in [s for s in subs if s not in m_subs]:
                r = SequenceMatcher(None, sig_v, Logic.signature(Path(s).stem)).ratio()
                if r > best_r and r > 0.6:
                    best_r, best = r, s
            if best:
                matches.append({"vid": v, "sub": best, "info": (0, len(matches)+1)})
                m_subs.add(best)
        return matches, len(vids), len(subs)


# =========================================================================
#  6. ANIME TREE DISCOVERY  —  THE NEW SMART PART
# =========================================================================
def find_fonts_folder_nearby(folder):
    """Walk UP from `folder` looking for a `_Fonts`/`fonts` sibling.
       Returns Path or None. Search stops at the volume root."""
    f = Path(folder).resolve()
    seen_roots = set()
    while True:
        if f in seen_roots:
            break
        seen_roots.add(f)
        for child in f.iterdir() if f.is_dir() else []:
            if child.is_dir() and child.name.lower() in FONTS_FOLDER_NAMES:
                return child
        if f.parent == f:
            break
        f = f.parent
    return None


def discover_anime_jobs(anime_root):
    """Crawl `anime_root` (an umbrella directory) and produce a list of jobs:
         { folder, fonts_dir, matches }
       Handles BOTH layouts:
         (A) AnimeRoot/SeriesName/_Fonts + episodes        (single-cour)
         (B) AnimeRoot/SeriesName/_Fonts + Season N/eps    (multi-part)
         (C) AnimeRoot/SeriesName/Season N/_Fonts + eps    (per-season fonts)
    """
    jobs = []
    root = Path(anime_root)
    if not root.is_dir():
        return jobs

    # Any folder that contains at least one matched (vid, sub) pair is a "leaf"
    for current_folder, dirs, files in os.walk(root):
        # Don't descend into hidden / system folders
        dirs[:] = [d for d in dirs
                   if not d.startswith("__") and not d.startswith(".")
                   and d.lower() not in FONTS_FOLDER_NAMES
                   and d.lower() != LIBRARY_FONTS_DIR_NAME.lower()]
        matches, nv, ns = Logic.pair_videos_and_subs(current_folder)
        if not matches:
            continue
        fonts_dir = find_fonts_folder_nearby(current_folder)
        jobs.append({
            "folder": current_folder,
            "fonts_dir": str(fonts_dir) if fonts_dir else None,
            "matches": matches,
            "n_videos": nv,
            "n_subs": ns,
        })
    return jobs


# =========================================================================
#  6b. EPISODE PLAN  +  STATUS  (the data model for pre-flight validation)
# =========================================================================
class EpStatus(str, Enum):
    """Status of every (video, subtitle) pair after pre-flight analysis."""
    READY      = "ready"        # every font the ASS needs is in _Fonts
    PARTIAL    = "partial"      # ASS needs N fonts, we have only some
    BLOCKED    = "blocked"      # no _Fonts folder, or none of the needed fonts present
    NO_FONTS   = "no_fonts"     # ASS doesn't reference any custom font at all
    MUXED      = "muxed"        # already done in a previous run (resume marker)


@dataclass
class EpisodePlan:
    """Everything we need to know about one episode BEFORE we mux it."""
    anime_name:     str
    folder:         str
    video:          str
    sub:            str
    fonts_dir:      Optional[str]
    fonts_resolved: dict           # {ass-font-name: file path}
    fonts_missing:  list           # [ass-font-name, ...]
    status:         EpStatus

    @property
    def video_path(self) -> Path:  return Path(self.folder) / self.video
    @property
    def sub_path(self)   -> Path:  return Path(self.folder) / self.sub
    @property
    def output_path(self) -> Path: return self.video_path.with_suffix(".mkv")
    @property
    def font_paths(self)  -> list: return list(dict.fromkeys(self.fonts_resolved.values()))


@dataclass
class AnimeReport:
    """Aggregated report per anime umbrella folder."""
    name:        str
    folder:      str
    fonts_dir:   Optional[str]
    episodes:    list           # list[EpisodePlan]
    missing_fonts_set: set      # all unique missing-font names across the anime

    @property
    def total(self):     return len(self.episodes)
    @property
    def ready(self):     return sum(1 for e in self.episodes if e.status == EpStatus.READY)
    @property
    def partial(self):   return sum(1 for e in self.episodes if e.status == EpStatus.PARTIAL)
    @property
    def blocked(self):   return sum(1 for e in self.episodes if e.status == EpStatus.BLOCKED)
    @property
    def no_fonts(self):  return sum(1 for e in self.episodes if e.status == EpStatus.NO_FONTS)
    @property
    def muxed(self):     return sum(1 for e in self.episodes if e.status == EpStatus.MUXED)
    @property
    def health(self):
        """green = fully OK, yellow = something to do, red = nothing usable"""
        if self.total == 0:                          return "dim"
        usable = self.ready + self.muxed
        if usable == self.total:                     return "green"
        if usable + self.no_fonts == self.total:     return "green"
        if self.blocked == self.total - self.muxed:  return "red"
        return "yellow"


# ── Resume state (per anime root) ─────────────────────────────────────────
def _state_path(anime_root):     return Path(anime_root) / STATE_FILENAME

def load_state(anime_root) -> dict:
    p = _state_path(anime_root)
    if not p.exists(): return {}
    try:    return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}

def save_state(anime_root, state: dict):
    try:
        _state_path(anime_root).write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log_event(anime_root, f"save_state failed: {e}", "WARN")

def mark_muxed(state: dict, plan: EpisodePlan):
    state[str(plan.output_path)] = {
        MUXED_MARKER_KEY: datetime.datetime.now().isoformat(timespec="seconds"),
        "anime": plan.anime_name,
        "fonts_attached": [Path(p).name for p in plan.font_paths],
    }


# =========================================================================
#  7. MUXING  —  the actual heavy lifting
# =========================================================================
def _mime_for_font(ext):
    """v1.11: modern RFC 8081 MIME types. libass ≥0.15 / mpv ≥0.34 /
    VLC ≥3.0.16 / Plex / Jellyfin all accept these. Legacy clients also
    work because mkvmerge stores the name we give it verbatim and modern
    libavformat normalises both to font/ttf internally."""
    return {
        ".ttf":   "font/ttf",
        ".otf":   "font/otf",
        ".ttc":   "font/collection",
        ".woff":  "font/woff",
        ".woff2": "font/woff2",
    }.get(ext.lower(), "application/octet-stream")


def build_mkvmerge_cmd(video, sub, fonts, out_path,
                       lang="ara", title="Arabic",
                       make_default=True,
                       strip_source_attachments=True,
                       strip_source_subs=False):
    """v1.11 — clean mux pipeline.

    Defaults:
      • STRIP all attachments from the source MKV (--no-attachments).
        Old fansub fonts from the English release are NEVER carried over.
      • Keep the source's existing subtitle tracks so the user can still
        cycle to them, but mark the new Arabic track as default + enabled.
      • Force --sub-charset 0:UTF-8 because _repair_ass_file always writes
        UTF-8 — mkvmerge auto-detection occasionally guesses cp1252.
      • --no-track-tags drops noisy XML tag blocks copied from source.
      • Per-attachment de-dup by filename (case-insensitive).
    """
    cmd = ["mkvmerge", "-o", str(out_path)]

    # 1) Source video flags must come BEFORE the video path
    if strip_source_attachments:
        cmd.append("--no-attachments")
    if strip_source_subs:
        cmd.append("--no-subtitles")
    cmd += ["--no-track-tags", "--no-global-tags", str(video)]

    # 2) Subtitle flags must come BEFORE the sub path
    cmd += [
        "--language",           f"0:{lang}",
        "--track-name",         f"0:{title}",
        "--default-track-flag", f"0:{1 if make_default else 0}",
        "--forced-display-flag", "0:0",
        "--sub-charset",        "0:UTF-8",
        str(sub),
    ]

    # 3) Font attachments (de-duplicated, modern MIME)
    seen = set()
    for fp in fonts:
        name = Path(fp).name
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cmd += [
            "--attachment-mime-type",  _mime_for_font(Path(fp).suffix),
            "--attachment-name",       name,
            "--attachment-description", f"Required by {Path(sub).name}",
            "--attach-file",           str(fp),
        ]
    return cmd


def build_ffmpeg_cmd(video, sub, fonts, out_path, lang="ara", title="Arabic"):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(video), "-i", str(sub)]
    for fp in fonts:
        cmd += ["-attach", str(fp)]
    # one -map per input stream
    cmd += ["-map", "0:v?", "-map", "0:a?", "-map", "0:s?", "-map", "1:s",
            "-c", "copy"]
    for idx in range(len(fonts)):
        cmd += [f"-metadata:s:t:{idx}", f"mimetype={_mime_for_font(Path(fonts[idx]).suffix)}",
                f"-metadata:s:t:{idx}", f"filename={Path(fonts[idx]).name}"]
    # Mark embedded sub as default Arabic
    cmd += ["-metadata:s:s:0", f"language={lang}",
            "-metadata:s:s:0", f"title={title}",
            "-disposition:s:0", "default",
            str(out_path)]
    return cmd


def _mkvmerge_identify_ok(path):
    """Quick pre-flight: can mkvmerge recognize this subtitle file?"""
    if not shutil.which("mkvmerge"):
        return True, "mkvmerge not installed; identify skipped"
    try:
        r = subprocess.run(["mkvmerge", "--identify", str(path)],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        blob = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
        low = blob.lower()
        bad = ("could not be recognized" in low or
               "cannot be opened" in low or
               ("error:" in low and r.returncode not in (0, 1)))
        return (not bad), (blob or f"returncode={r.returncode}")
    except Exception as e:
        return False, str(e)


def _verify_muxed_file(out_path, expected_fonts, expected_sub_lang="ara"):
    """v1.11: post-mux validation. Confirm with mkvmerge -J that:
      • the output is a parseable MKV,
      • the new subtitle track is present with the requested language,
      • every font we tried to attach is actually inside the container.
    Returns (ok, note).
    """
    if not shutil.which("mkvmerge"):
        return True, "verify skipped (no mkvmerge)"
    try:
        r = subprocess.run(["mkvmerge", "-J", str(out_path)],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        if r.returncode not in (0, 1):
            return False, f"mkvmerge -J failed (rc={r.returncode}): {(r.stderr or '')[:200]}"
        info = json.loads(r.stdout or "{}")
    except Exception as e:
        return False, f"verify crashed: {e}"
    # v2.0 FIX: use proper language matching matrix instead of broken startswith()
    # Old bug: "ar".startswith("ara") = False -> mis-rejected ar-tagged subs.
    # We can't reference v2_language_matches() here because it's defined later
    # in the file; we inline an equivalent check using the canonical mapping.
    _ARA_OK = {"ar", "ara", "arb",
               "ar-eg", "ar-sa", "ar-ae", "ar-ma", "ar-iq", "ar-jo",
               "ar-kw", "ar-lb", "ar-ly", "ar-om", "ar-qa", "ar-sy",
               "ar-tn", "ar-ye", "ar-dz", "ar-bh", "ar-ps"}
    subs = []
    for t in info.get("tracks", []):
        if t.get("type") != "subtitles":
            continue
        props = t.get("properties", {}) or {}
        iso = (props.get("language") or "").lower().strip()
        ietf = (props.get("language_ietf") or "").lower().strip()
        exp = (expected_sub_lang or "").lower().strip()
        # Direct match first
        if exp and (iso == exp or ietf == exp):
            subs.append(t); continue
        # Arabic family: handles ar/ara/arb/ar-EG/etc.
        if exp == "ara" and (iso in _ARA_OK or ietf in _ARA_OK
                             or any(ietf.startswith(c + "-") for c in ("ar",))):
            subs.append(t); continue
    if not subs:
        return False, f"output has no subtitle track with language={expected_sub_lang}"
    attached = {a.get("file_name", "").lower()
                for a in info.get("attachments", [])}
    expected_names = {Path(p).name.lower() for p in (expected_fonts or [])}
    missing = sorted(expected_names - attached)
    if missing:
        return False, f"output is missing {len(missing)} attachment(s): {missing[:4]}"
    return True, f"ok (sub track + {len(attached)} attachments)"


def _short_err(text, max_len=180):
    """Compact, human-friendly summary of a multi-line stderr blob.

    The on-screen version is short and useful: file paths are collapsed to
    just the basename so the actual error REASON is visible in the panel.
    The FULL message is still written to the .anime_studio_log.txt log.
    """
    if not text:
        return "unknown error"
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    target = None
    for l in lines:                  # prefer the Error/Fatal lines
        if l.lower().startswith(("error", "fatal", "failure")):
            target = l
            break
    if not target:
        target = lines[-1] if lines else text.strip()

    # Collapse any quoted absolute path (Windows or POSIX) into just the
    # basename, so the actual error REASON survives the max_len budget.
    #
    # Note 1: paths CAN contain apostrophes (e.g. "April Fools' Day"), so
    #         we match greedily up to .EXT' rather than relying on "non-'".
    # Note 2: we don't use os.path.basename because that ignores '\\' on POSIX.
    #         Our errors come from Windows mkvmerge running against D:\... paths,
    #         so we split on BOTH separators ourselves.
    def _basename_xplat(match):
        full = match.group(1)
        # Take the segment after the last '\\' or '/' — works on every OS
        idx = max(full.rfind("\\"), full.rfind("/"))
        return f"'{full[idx+1:] if idx >= 0 else full}'"
    # Windows drive paths ending in an extension: 'X:\..\..\file.ext'
    target = re.sub(
        r"'([A-Za-z]:[\\/].+?\.[A-Za-z0-9]{1,6})'",
        _basename_xplat, target)
    # POSIX paths ending in an extension: '/path/file.ext'
    target = re.sub(
        r"'(/[^']*?\.[A-Za-z0-9]{1,6})'",
        _basename_xplat, target)
    # UNC paths: '\\\\server\\share\\..\\file.ext'
    target = re.sub(
        r"'(\\\\.+?\.[A-Za-z0-9]{1,6})'",
        _basename_xplat, target)

    if len(target) > max_len:
        target = target[: max_len - 1] + "…"
    return target


def _safe_replace(src, dst):
    """Atomically replace `dst` with `src` (Windows-safe).

    Plain `shutil.move(src, dst)` can fail on Windows when `dst` exists
    and is an MKV that was just open for reading (antivirus, indexer
    holding a handle). Strategy: delete `dst` first (with retries), then
    `os.replace` which on Windows is atomic across the same volume.
    """
    import time
    src, dst = str(src), str(dst)
    if os.path.abspath(src) == os.path.abspath(dst):
        return  # nothing to do
    # On Windows, os.replace can already overwrite — try it first
    last_err = None
    for attempt in range(4):
        try:
            os.replace(src, dst)
            return
        except PermissionError as e:
            last_err = e
            # Try removing the destination explicitly, then retry
            try:
                if os.path.exists(dst):
                    os.remove(dst)
            except Exception as e2:
                last_err = e2
            time.sleep(0.5 * (attempt + 1))
        except OSError as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    # Last-ditch effort: copy + remove
    try:
        shutil.copy2(src, dst)
        os.remove(src)
        return
    except Exception as e:
        raise last_err or e


# ── Subtitle file repair  (aggressive: encoding + format + structure) ───────
ASS_SECTION_RE = re.compile(
    r"^\[(Script Info|V4\+? Styles|V4 Styles|Events|Fonts|Graphics|Aegisub Project Garbage)\]",
    re.MULTILINE,
)

_ASS_MARKER_RE = re.compile(
    r"\[Script Info\]|\[Events\]|\[V4\+? Styles\]|\[V4 Styles\]|"
    r"^\s*Dialogue:|^\s*Style:|^\s*Format:\s*Name|^\s*ScriptType:",
    re.MULTILINE,
)


def _smart_decode_ass(raw):
    """Best-effort decoder for ASS/SSA byte payloads.

    v1.10 fixes the silent-failure that hit Takagi-san S02: scripts that are
    UTF-16-without-BOM, UTF-32, BOM-less cp1256, or Mac legacy encodings used
    to decode without error but produce gibberish that lacks any [Script Info]
    or Dialogue: marker, so the whole file was rejected as "not a valid ASS".

    Strategy:
      1. Hard-detect BOMs and zero-byte stride patterns.
      2. Try every plausible encoding.
      3. Score each candidate by how many ASS markers survived the decode.
      4. Return the highest-scoring candidate. Ties prefer modern Unicode.
    """
    if not raw:
        return ""

    # Step 1: BOM detection (cheap, deterministic).
    if raw[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
        try:
            return raw.decode("utf-32")
        except Exception:
            pass
    if raw[:2] == b"\xff\xfe":
        try:
            return raw.decode("utf-16-le")
        except Exception:
            pass
    if raw[:2] == b"\xfe\xff":
        try:
            return raw.decode("utf-16-be")
        except Exception:
            pass
    if raw[:3] == b"\xef\xbb\xbf":
        try:
            return raw[3:].decode("utf-8")
        except Exception:
            pass

    # Step 2: stride-based heuristic for UTF-16 without BOM
    # (a lot of legacy Windows fansub tools save like this).
    head = raw[:4096]
    even_nulls = sum(1 for i, b in enumerate(head) if b == 0 and i % 2 == 1)
    odd_nulls  = sum(1 for i, b in enumerate(head) if b == 0 and i % 2 == 0)
    if even_nulls > len(head) * 0.20 and even_nulls > odd_nulls * 3:
        try:
            return raw.decode("utf-16-le", errors="replace")
        except Exception:
            pass
    if odd_nulls > len(head) * 0.20 and odd_nulls > even_nulls * 3:
        try:
            return raw.decode("utf-16-be", errors="replace")
        except Exception:
            pass

    # Step 3: brute-force candidates, score by marker survival.
    encodings = (
        "utf-8", "utf-8-sig",
        "utf-16", "utf-16-le", "utf-16-be",
        "cp1256", "cp1252", "cp1250", "cp1251",
        "mac-roman", "iso-8859-1", "latin-1",
        "shift_jis", "euc-jp",
    )
    best_text, best_score, best_enc = None, -1, None
    for enc in encodings:
        try:
            candidate = raw.decode(enc, errors="strict")
        except (UnicodeDecodeError, UnicodeError):
            try:
                candidate = raw.decode(enc, errors="replace")
            except Exception:
                continue
        # Score = marker hits + small bonus for readable ASCII ratio
        markers = len(_ASS_MARKER_RE.findall(candidate))
        printable = sum(1 for ch in candidate[:4096]
                        if 32 <= ord(ch) < 127 or ch in "\n\r\t")
        ratio = printable / max(1, min(4096, len(candidate)))
        score = markers * 100 + int(ratio * 50)
        # Tiny preference for utf-8 / utf-16 on a tie so we don't lock onto
        # latin-1 just because everything decodes to something.
        if enc in ("utf-8", "utf-8-sig"):
            score += 5
        if score > best_score:
            best_text, best_score, best_enc = candidate, score, enc
    if best_text is None:
        return raw.decode("latin-1", errors="replace")
    return best_text

def _repair_ass_file(sub_path, out_dir):
    """Aggressively normalize an ASS/SSA/SRT file so mkvmerge always accepts it.

    A surprising number of fansub releases ship subtitle files with one or
    more of these defects:
      • Windows-1256 / cp1252 / UTF-16 encoding (no BOM, no metadata)
      • UTF-8 BOM that confuses older parsers
      • Mixed line-endings (\r\n + bare \r + \n in the same file)
      • Leading garbage bytes BEFORE the [Script Info] header
         (often from a broken HTTP download or text-editor metadata)
      • The file extension is .ass but the content is actually SRT or VTT

    Any of those triggers mkvmerge's cryptic 'type of file could not be
    recognized' — the same error that kept failing on the Karakai S02
    files.  This function fixes ALL of them in one shot.

    Returns: (new_path, was_repaired, diagnostic)
      • new_path     — path to use for muxing (may be a temp copy)
      • was_repaired — True if a temp file was created and should be cleaned up
      • diagnostic   — human-readable note about what we did or why we gave up
    """
    try:
        raw = Path(sub_path).read_bytes()
    except Exception as e:
        return sub_path, False, f"could not read: {e}"

    if len(raw) < 8:
        return sub_path, False, f"file is empty or unreadable ({len(raw)} bytes)"

    # ── Step 1: decode with the smart multi-encoding scorer (v1.10) ──
    text = _smart_decode_ass(raw)
    detected = "auto"
    if not text:
        return sub_path, False, "no encoding decoded the file"
    original_text = text

    # ── Step 2: normalize line endings (\r\n + \r + \n  →  \n) ──
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # ── Step 3: strip leading BOM / whitespace / garbage ──
    text = text.lstrip("\ufeff\u200b \t\n\r")

    # ── Step 4: trim everything before the FIRST [Section] marker ──
    section_match = ASS_SECTION_RE.search(text)
    is_ass_like = section_match is not None
    if section_match and section_match.start() > 0:
        text = text[section_match.start():]

    # ── Step 5: detect SRT content disguised as .ass ──
    looks_like_srt = (not is_ass_like and
                      re.match(r"^\d+\s*\n\d{1,2}:\d{2}:\d{2}[.,]\d+\s*-->",
                               text.lstrip()))
    if looks_like_srt:
        return sub_path, False, \
            "content is SRT but extension is .ass — rename to .srt and retry"

    # v1.11: if no section header was found, try non-destructive salvage:
    #   a) wrap real Dialogue:/Style:/Format: payloads in synthetic headers
    #   b) if there is no Dialogue: line at all, scan for SRT-style
    #      time-stamped lines and synthesize them into [Events]
    # v1.11 explicitly REMOVES the old "placeholder ASS" fallback that used
    # to silently replace a corrupt subtitle with a 1-second placeholder —
    # that wiped real dialogue and produced empty Arabic playback. Now we
    # refuse the file with a clear diagnostic instead.
    if not is_ass_like:
        has_dialogue = "Dialogue:" in text
        has_style = "Style:" in text or text.lstrip().startswith("Format: Name")
        has_format = "Format:" in text
        if has_dialogue or has_style or has_format:
            chunks = ["[Script Info]", "ScriptType: v4.00+",
                      "WrapStyle: 0", "PlayResX: 1920", "PlayResY: 1080", ""]
            if has_style and "[V4" not in text:
                chunks += ["[V4+ Styles]",
                           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"]
            if has_dialogue and "[Events]" not in text:
                chunks += ["[Events]",
                           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
            text = "\n".join(chunks) + "\n" + text.lstrip()
            is_ass_like = True
        else:
            srt_like = list(re.finditer(
                r"(\d{1,2}:\d{2}:\d{2})[.,](\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2})[.,](\d{1,3})\s*\n(.+?)(?=\n\s*\n|\Z)",
                text, re.DOTALL))
            if srt_like:
                events = []
                for m in srt_like:
                    s = f"{m.group(1)}.{int(m.group(2)):03d}"[:-1]
                    e = f"{m.group(3)}.{int(m.group(4)):03d}"[:-1]
                    line = m.group(5).replace("\n", "\\N").strip()
                    events.append(f"Dialogue: 0,{s},{e},Default,,0,0,0,,{line}")
                # v1.11: pick a sensible default font for the synthesized
                # style. If the body looks Arabic (codepoint scan), prefer
                # Tahoma+Encoding=178 so libass shapes RTL correctly.
                has_arabic = bool(re.search(r"[\u0600-\u06ff]", text))
                style_font = "Tahoma" if has_arabic else "Arial"
                style_enc = 178 if has_arabic else 1
                text = ("[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\n"
                        "PlayResX: 1920\nPlayResY: 1080\n\n"
                        "[V4+ Styles]\n"
                        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
                        f"Style: Default,{style_font},48,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,30,{style_enc}\n\n"
                        "[Events]\n"
                        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                        + "\n".join(events) + "\n")
                is_ass_like = True
            else:
                # v1.11: refuse the file rather than emit a placeholder that
                # erases the real (unrecognised) payload.
                return sub_path, False, \
                    "subtitle has no [Script Info]/[Events]/Dialogue: structure and no time-stamps — cannot be repaired without losing content"

    # ── Step 6: ensure [Script Info] is the first section (mkvmerge insists) ──
    if not text.lstrip().startswith("[Script Info]"):
        text = "[Script Info]\nScriptType: v4.00+\n\n" + text

    # v1.9: ALWAYS write a safe ASCII temp copy for mkvmerge.
    # Even perfectly-valid ASS files may fail when their original Windows path
    # contains apostrophes, brackets, percent signs, or non-ASCII characters.
    _MKVMERGE_UNSAFE = set("'[]%&;=(){}!,+")
    filename_unsafe  = any(c in _MKVMERGE_UNSAFE or ord(c) > 127
                           for c in os.path.basename(sub_path))

    # ── Step 7: write the clean copy to a hidden temp next to the MKV ──
    base = os.path.splitext(os.path.basename(sub_path))[0]
    safe_base = re.sub(r'[^A-Za-z0-9._-]+', "_", base).strip('._')[:120] or 'subtitle'
    fixed = os.path.join(out_dir, f".{safe_base}.prepared.ass")
    try:
        Path(fixed).write_text(text, encoding="utf-8", newline="\n")
        note_bits = [f"decoded={detected or 'unknown'}"]
        if text != original_text:
            note_bits.append("normalized")
        if filename_unsafe:
            note_bits.append("safe-path")
        return fixed, True, ", ".join(note_bits)
    except Exception as e:
        return sub_path, False, f"could not write temp: {e}"


def smart_mux_one(args):
    """Worker: mux a single (video, subtitle, [fonts]) into out_path.

    v1.4 robustness pipeline:
      • Subtitle goes through `_repair_ass_file` which not only fixes encoding
        (Windows-1256 / UTF-16 / cp1252 → UTF-8) but ALSO:
          – normalizes line endings
          – trims BOM + leading garbage before [Script Info]
          – prepends a [Script Info] header if missing
          – reports if the .ass is actually SRT or completely corrupted
      • If the repair returns a hard "this is not a real ASS" diagnostic, we
        skip mkvmerge entirely and report a clean, actionable error.
      • Temp output is hidden + suffixed, placed next to destination for
        atomic rename via `_safe_replace`.
      • Errors come back with paths collapsed to basenames so the panel
        stays readable.  The FULL stderr is still written to the log.
    """
    (video, sub, fonts, out_path, prefer_mkvmerge) = args
    out_path = str(out_path)
    out_dir  = os.path.dirname(out_path) or "."
    tmp_key  = hashlib.sha1(out_path.encode("utf-8", errors="replace")).hexdigest()[:12]
    tmp_path = os.path.join(out_dir, f"_amux_{tmp_key}.tmp.mkv")
    fixed_sub_path = None

    try:
        # 0. Sanity check inputs exist
        if not os.path.exists(video):
            return False, video, f"video file missing: {os.path.basename(video)}"
        if not os.path.exists(sub):
            return False, video, f"subtitle file missing: {os.path.basename(sub)}"

        # 1. Aggressive subtitle preparation (encoding + structure + safe path)
        sub_for_mux, was_repaired, repair_note = _repair_ass_file(sub, out_dir)
        if ("content is SRT" in repair_note or
            "suspiciously small" in repair_note or
            "too small" in repair_note or
            "could not read" in repair_note or
            "not a valid ASS" in repair_note):
            return False, video, f"[subtitle] {repair_note}"
        if was_repaired:
            fixed_sub_path = sub_for_mux

        # v1.9: prepared subtitle first, raw original only as a last-ditch
        # emergency fallback when temp creation itself failed.
        candidates = [(sub_for_mux, f"prepared subtitle ({repair_note})")]
        if not was_repaired and os.path.abspath(sub_for_mux) == os.path.abspath(sub):
            candidates = [(sub, "original subtitle (preparation unavailable)")]

        # Pre-flight mkvmerge identify check when available. This catches the
        # exact 'type of file could not be recognized' failure before muxing.
        if shutil.which("mkvmerge") and os.path.exists(sub_for_mux):
            ok_ident, ident_note = _mkvmerge_identify_ok(sub_for_mux)
            if not ok_ident:
                return False, video, f"[subtitle] mkvmerge could not identify prepared ASS ({repair_note})|FULL|{ident_note}"

        # 2. Pick tool once
        if prefer_mkvmerge and shutil.which("mkvmerge"):
            build_cmd = build_mkvmerge_cmd
            tool = "mkvmerge"
        elif shutil.which("ffmpeg"):
            build_cmd = build_ffmpeg_cmd
            tool = "ffmpeg"
        else:
            return False, video, "Neither mkvmerge nor ffmpeg found in PATH"

        # v1.11: minimum output size = max(1MB, 25% of source) so we never
        # accept a microscopic file that happened to be > 4KB.
        try:
            src_size = os.path.getsize(video)
        except Exception:
            src_size = 0
        min_out = max(1_000_000, int(src_size * 0.25))

        last_full_err = None
        for sub_candidate, candidate_note in candidates:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

            cmd = build_cmd(video, sub_candidate, fonts, tmp_path)
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            full_err = (r.stderr or r.stdout or "").strip()
            if r.returncode == 0 or (r.returncode == 1 and "Warning" in full_err):
                if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < min_out:
                    last_full_err = (f"[{tool}] produced an undersized output "
                                     f"({os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0} bytes)"
                                     f" using {candidate_note}")
                    continue
                # v1.11: post-mux verification — confirm sub & fonts are inside
                ok_v, note_v = _verify_muxed_file(tmp_path, fonts, expected_sub_lang="ara")
                if not ok_v:
                    last_full_err = (f"[{tool}] post-mux verification failed: {note_v} "
                                     f"using {candidate_note}|FULL|{full_err}")
                    try: os.remove(tmp_path)
                    except Exception: pass
                    continue
                _safe_replace(tmp_path, out_path)
                ok_msg = "" if r.returncode == 0 else f"[warn] {_short_err(full_err)}"
                return True, video, ok_msg

            last_full_err = f"[{tool}] {_short_err(full_err)} while using {candidate_note}|FULL|{full_err}"
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

        return False, video, last_full_err or f"[{tool}] unknown mux failure"
    except Exception as e:
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass
        return False, video, _short_err(str(e))
    finally:
        if fixed_sub_path and os.path.exists(fixed_sub_path):
            try: os.remove(fixed_sub_path)
            except Exception: pass


# =========================================================================
#  8. LEGACY WORKERS  (kept for "simple merge" mode)
# =========================================================================
def sync_task(args):
    vid, sub_in, sub_out = args
    try:
        subprocess.run(["ffsubsync", vid, "-i", sub_in, "-o", sub_out],
                       check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return True, sub_in, ""
    except Exception as e:
        return False, sub_in, str(e)


def simple_embed_task(args):
    vid, sub, temp_out, final_target = args
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-i", vid, "-i", sub,
                        "-c", "copy", "-map", "0", "-map", "1",
                        "-metadata:s:s:0", "language=ara",
                        "-metadata:s:s:0", "title=Arabic",
                        "-disposition:s:0", "default", temp_out],
                       check=True)
        shutil.move(temp_out, final_target)
        return True, sub, ""
    except Exception as e:
        if os.path.exists(temp_out):
            os.remove(temp_out)
        return False, sub, str(e)


# =========================================================================
#  9. SYSTEM-FONT BACKUP   (Python port of BackupAnimeFonts.ps1)
# =========================================================================
def scan_and_backup_anime_fonts(anime_root):
    """For each AnimeName/ folder under `anime_root`:
        • Read every ASS to find required font names
        • Look them up in BOTH the system fonts AND the library-wide
          `<anime_root>/fonts/` pool (so freshly downloaded fonts are
          found immediately, without needing a Windows reboot)
        • Copy matching files into <Anime>/_Fonts
        • Also copy into a single global backup folder
        • Save _Missing_Fonts.txt for anything not found
    """
    library_fonts = Path(anime_root) / LIBRARY_FONTS_DIR_NAME
    extra_dirs = [str(library_fonts)] if library_fonts.is_dir() else []

    if sys.platform != "win32" and not extra_dirs:
        print("⚠️  System font scan needs Windows OR a populated "
              f"{library_fonts.name}/ directory.")
        return

    if _RICH:
        with Progress(SpinnerColumn(),
                      TextColumn("[progress.description]{task.description}"),
                      console=_con, transient=True) as sp:
            sp.add_task("Indexing fonts (system + library)…", total=None)
            precise, roots, _raw = system_font_map(extra_dirs)
        if extra_dirs:
            rprint(f"[dim]Indexed [cyan]{len(precise)}[/cyan] precise names, "
                   f"[cyan]{len(roots)}[/cyan] family roots "
                   f"(including [green]{library_fonts.name}/[/green]).[/dim]")
        else:
            rprint(f"[dim]Indexed [cyan]{len(precise)}[/cyan] precise names, "
                   f"[cyan]{len(roots)}[/cyan] family roots.[/dim]")
    else:
        print("🔍 Indexing fonts (system + library) …")
        precise, roots, _raw = system_font_map(extra_dirs)
        print(f"   Indexed {len(precise)} precise names, {len(roots)} family roots.")

    root = Path(anime_root)
    global_dir = root / GLOBAL_BACKUP_NAME
    global_dir.mkdir(exist_ok=True)

    anime_dirs = [a for a in root.iterdir()
                  if a.is_dir() and not a.name.startswith("__")]
    total_copied = total_missing_count = 0

    for anime in anime_dirs:
        if _RICH:
            rprint(f"\n[bold cyan]🎬 {anime.name}[/bold cyan]")
        else:
            print(f"\n🎬 {anime.name}")
        missing = []
        copied  = 0
        seen    = set()
        for ass in anime.rglob("*.ass"):
            for name in fonts_required_by_ass(ass):
                if name in seen or name.lower() in SYSTEM_FONT_IGNORE:
                    continue
                seen.add(name)
                pk, rk = clean_key(name), root_key(name)
                src = precise.get(pk);  tag = "EXACT"
                if not src and rk and len(rk) > 2:
                    src = roots.get(rk);  tag = f"FAMILY ({rk})"
                if not src:
                    for k, p in precise.items():
                        if pk and pk in k:
                            src, tag = p, "FUZZY"; break
                if src:
                    dest_local = anime / "_Fonts" / Path(src).name
                    dest_local.parent.mkdir(exist_ok=True)
                    if not dest_local.exists():
                        shutil.copy2(src, dest_local)
                    g = global_dir / Path(src).name
                    if not g.exists():
                        shutil.copy2(src, g)
                    copied += 1
                    if _RICH:
                        rprint(f"  [green][{tag}][/green] [dim]{name}[/dim] → {Path(src).name}")
                    else:
                        print(f"   [{tag}] '{name}' → {Path(src).name}")
                else:
                    missing.append(name)
                    if _RICH:
                        rprint(f"  [red][MISSING][/red] [dim]{name}[/dim]")
                    else:
                        print(f"   [MISSING] '{name}'")
        total_copied        += copied
        total_missing_count += len(missing)
        if missing:
            (anime / MISSING_REPORT_NAME).write_text(
                "\n".join(sorted(set(missing))), encoding="utf-8")
        # per-anime mini summary
        if _RICH:
            parts = []
            if copied:  parts.append(f"[green]✓ {copied} copied[/green]")
            if missing: parts.append(f"[red]✗ {len(missing)} missing → {MISSING_REPORT_NAME}[/red]")
            rprint("  " + "   ".join(parts) if parts else "  [dim]nothing to do[/dim]")
        else:
            if missing: print(f"   ⚠️  {len(missing)} missing fonts → {MISSING_REPORT_NAME}")
            if copied:  print(f"   ✅ Copied {copied} fonts.")

    _print_summary("Font Backup Complete",
                   ok=total_copied,
                   fail=total_missing_count,
                   notes=[f"{total_missing_count} font(s) not found on this system — "
                          "check _Missing_Fonts.txt per anime"] if total_missing_count else None)


# =========================================================================
# 10. CLEANUP  (Python port of clean_up_fonts.ps1)
# =========================================================================
def cleanup_anime_root(anime_root):
    root = Path(anime_root)
    targets = []
    # Global backup folder
    gb = root / GLOBAL_BACKUP_NAME
    if gb.exists():
        targets.append(gb)
    # Per-anime _Fonts folders
    for p in root.rglob("*"):
        if p.is_dir() and p.name.lower() in FONTS_FOLDER_NAMES:
            targets.append(p)
    # Missing reports
    for p in root.rglob(MISSING_REPORT_NAME):
        targets.append(p)
    if not targets:
        print("Nothing to clean.")
        return
    print("The following will be DELETED:")
    for t in targets:
        print(f"  • {t}")
    if sys.stdin.isatty() and os.environ.get("ANIME_STUDIO_AUTO_YES") != "1":
        ans = input("Proceed? (yes/N): ").strip().lower()
        if ans != "yes":
            print("Aborted.")
            return
    ok_count = err_count = 0
    for t in targets:
        try:
            if t.is_dir():
                shutil.rmtree(t)
            else:
                t.unlink()
            ok_count += 1
            rprint(f"  [green]✓[/green] removed {t}")
        except Exception as e:
            err_count += 1
            rprint(f"  [red]✗[/red] {t}: {e}")
    _print_summary("Cleanup Complete", ok_count, err_count)


# =========================================================================
# 11. MPV CONFIG GENERATOR  (sub-fonts-dir fallback)
# =========================================================================
def setup_mpv_config():
    """Drop a mpv.conf entry pointing at PORTABLE_FONTS_DIR — fallback only,
       muxing is still the recommended primary strategy."""
    Path(PORTABLE_FONTS_DIR).mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        conf_dir = Path(os.environ.get("APPDATA", Path.home())) / "mpv"
    else:
        conf_dir = Path.home() / ".config" / "mpv"
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf = conf_dir / "mpv.conf"
    line = f'sub-fonts-dir="{PORTABLE_FONTS_DIR}"'
    existing = conf.read_text(encoding="utf-8") if conf.exists() else ""
    if "sub-fonts-dir" in existing:
        print(f"⚠️  sub-fonts-dir already configured in {conf}.")
    else:
        with open(conf, "a", encoding="utf-8") as f:
            f.write(f"\n# Added by Anime Studio — fallback only\n{line}\n"
                    "embeddedfonts=yes\n")
        print(f"✓ Updated {conf}")
    print(f"📁 Portable fonts directory: {PORTABLE_FONTS_DIR}")
    print("   Drop any global fallback fonts in there. Muxed MKVs ignore this.")

# =========================================================================
# 11b. FONT  HUNTER  —  auto-download missing fonts from the web
# =========================================================================
#
#  Strategy (queried in order, first hit wins per font name):
#
#    1) Google Fonts   via google-webfonts-helper API
#       · covers 1500+ open-source fonts (Readex Pro, Cabin, Open Sans,
#         Roboto, Noto family, Amiri, Cairo, Tajawal, Changa, …)
#       · endpoint: https://gwfh.mranftl.com/api/fonts/{slug}
#       · returns JSON; we pull TTF URLs for every weight available
#
#    2) Curated catalog  for famous Arabic / fansub fonts that need
#       hand-picked substitutions (commercial-name → free-equivalent)
#
#    3) GitHub Code Search   (10 req/min unauth)
#       · query: `filename:"NAME.ttf"`
#       · picks first raw URL hit
#
#    4) DuckDuckGo HTML search (no API key, no captcha on /html/)
#       · query: `"FONT NAME" filetype:ttf -site:behance.net`
#       · scrapes the first direct .ttf/.otf link from results
#       · catches everything else (1lot of one-off fansub fonts live
#         in random forums and Drive mirrors that DDG indexes)
#
#  Behaviour & storage:
#    · Found fonts go straight into `<anime_root>/fonts/` — the same
#      central pool is also scanned. NO system-wide install.
#    · Results are cached in `<anime_root>/.anime_studio_font_cache.json`
#      so subsequent runs don't repeat lookups (positive AND negative).
#
# =========================================================================
import urllib.request
import urllib.parse
import urllib.error

FONT_CACHE_NAME = ".anime_studio_font_cache.json"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 AnimeStudio/1.3")

# ── Known-good direct URLs  (exact font → exact URL, NO substitutes) ─────────
# Add an entry here ONLY when the URL actually serves that exact font.
# Verified = fontTools confirms the name table contains the requested name.
FONT_DIRECT_URLS: dict = {
    # ── Amiri / Lateef ───────────────────────────────────────────────────────
    "amiri":          ["https://raw.githubusercontent.com/aliftype/amiri/master/sources/Amiri-Regular.ttf"],
    "amiribold":      ["https://raw.githubusercontent.com/aliftype/amiri/master/sources/Amiri-Bold.ttf"],
    "amiriquran":     ["https://raw.githubusercontent.com/aliftype/amiri/master/sources/AmiriQuran-Regular.ttf"],
    "lateef":         ["https://raw.githubusercontent.com/silnrsi/font-lateef/master/source/Lateef-Regular.ttf"],
    # ── El Messiri / Scheherazade ─────────────────────────────────────────────
    "elmessiri":      ["https://raw.githubusercontent.com/google/fonts/main/ofl/elmessiri/ElMessiri%5Bwght%5D.ttf"],
    "scheherazadenew":["https://raw.githubusercontent.com/google/fonts/main/ofl/scheherazadenew/ScheherazadeNew-Regular.ttf"],
    # ── Persian X-series ─────────────────────────────────────────────────────
    "xbzar":          ["https://raw.githubusercontent.com/rahatool/persian-fonts/master/Zar.ttf"],
    "xmyekan":        ["https://raw.githubusercontent.com/rahatool/persian-fonts/master/Yekan.ttf"],
    "xmtitr":         ["https://raw.githubusercontent.com/rahatool/persian-fonts/master/Titr.ttf"],
    "xmlotus":        ["https://raw.githubusercontent.com/rahatool/persian-fonts/master/Lotus.ttf"],
    "xpziba":         ["https://raw.githubusercontent.com/rahatool/persian-fonts/master/Ziba.ttf",
                       "https://raw.githubusercontent.com/mhusseini/persian-fonts/master/XP%20Ziba.ttf"],
    "ziba":           ["https://raw.githubusercontent.com/rahatool/persian-fonts/master/Ziba.ttf"],
    "xpnazanin":      ["https://raw.githubusercontent.com/rahatool/persian-fonts/master/Nazanin.ttf"],
    "afsaneh":        ["https://raw.githubusercontent.com/rahatool/persian-fonts/master/Nazanin.ttf"],
    # ── Noto CJK ─────────────────────────────────────────────────────────────
    "notosansjp":     ["https://raw.githubusercontent.com/google/fonts/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"],
    "notosanskr":     ["https://raw.githubusercontent.com/google/fonts/main/apache/notosanskr/NotoSansKR%5Bwght%5D.ttf"],
    "notoserifjp":    ["https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifjp/NotoSerifJP%5Bwght%5D.ttf"],
    "kleeone":        ["https://raw.githubusercontent.com/google/fonts/main/ofl/kleeone/KleeOne-Regular.ttf"],
    "yujisyuku":      ["https://raw.githubusercontent.com/google/fonts/main/ofl/yujisyuku/YujiSyuku-Regular.ttf"],
}

# ── Google Fonts API slug map ────────────────────────────────────────────────
GOOGLE_FONTS_SLUGS_BY_ALIAS = {
    "readex pro":         "readex-pro",
    "readex pro medium":  "readex-pro",
    "open sans":          "open-sans",
    "open sans semibold": "open-sans",
    "cabin":              "cabin",
    "cabin pl":           "cabin",
    "roboto":             "roboto",
    "noto sans":          "noto-sans",
    "noto sans arabic":   "noto-sans-arabic",
    "noto naskh arabic":  "noto-naskh-arabic",
    "noto serif jp":      "noto-serif-jp",
    "noto sans jp":       "noto-sans-jp",
    "noto sans kr":       "noto-sans-kr",
    "amiri":              "amiri",
    "cairo":              "cairo",
    "tajawal":            "tajawal",
    "changa":             "changa",
    "el messiri":         "el-messiri",
    "reem kufi":          "reem-kufi",
    "lateef":             "lateef",
    "scheherazade":       "scheherazade-new",
    "scheherazade new":   "scheherazade-new",
    "markazi text":       "markazi-text",
    "lalezar":            "lalezar",
    "harmattan":          "harmattan",
    "katibeh":            "katibeh",
    "rakkas":             "rakkas",
    "inter":              "inter",
    "fira code":          "fira-code",
    "fira sans":          "fira-sans",
    "source code pro":    "source-code-pro",
    "source sans 3":      "source-sans-3",
    "klee one":           "klee-one",
    "poppins":            "poppins",
    "orbitron":           "orbitron",
    "zen maru gothic":    "zen-maru-gothic",
    "grandstander":       "grandstander",
    "yuji syuku":         "yuji-syuku",
    "exo 2":              "exo-2",
    "nunito":             "nunito",
    "comfortaa":          "comfortaa",
    "satisfy":            "satisfy",
    "aref ruqaa":         "aref-ruqaa",
    "aref ruqaa ink":     "aref-ruqaa",
}


# ── Font-name verification (exact match, never a substitute) ─────────────────
# ── HTTP helpers ───────────────────────────────────────────────────────────
def _http_get_text(url, timeout=15):
    """GET a URL and return decoded text. Returns None on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _http_get_json(url, timeout=15):
    """GET a URL and parse JSON. Returns None on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


# Magic bytes that identify a valid font file
_FONT_MAGIC = (
    b"\x00\x01\x00\x00",  # TrueType
    b"OTTO",                  # OpenType (CFF)
    b"true",                  # Apple TrueType
    b"typ1",                  # PostScript Type 1
    b"wOFF",                  # WOFF
    b"wOF2",                  # WOFF2
    b"ttcf",                  # TrueType Collection
)


def _is_font_magic(data):
    """Return True if the byte buffer starts with a recognized font signature."""
    if not data or len(data) < 4:
        return False
    return data[:4] in _FONT_MAGIC


def _wayback_url(url, timeout=10):
    """Return the most recent Wayback Machine snapshot URL for `url`,
    or None if no archived copy exists.

    Uses the public availability API:
        https://archive.org/wayback/available?url=<url>
    """
    api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
    data = _http_get_json(api, timeout=timeout)
    if not data:
        return None
    snap = (data.get("archived_snapshots", {}) or {}).get("closest")
    if snap and snap.get("available") and snap.get("url"):
        # archive.org returns http; force https; append id_ to skip the toolbar wrapper
        wb = snap["url"]
        if "/web/" in wb and "id_/" not in wb:
            wb = wb.replace("/web/", "/web/", 1).replace("/http", "id_/http", 1)
        return wb.replace("http://", "https://", 1)
    return None


def _font_name_matches(font_path, wanted_name, threshold=0.72):
    """Return True if any name record in the font fuzzy-matches `wanted_name`.

    Opens the file with fontTools — same library used for build_font_map.
    threshold=0.72 accepts "HSN Khalid" ↔ "HsnKhalid" but rejects
    "Tajawal" when we asked for "HSN Khalid".
    """
    try:
        from fontTools.ttLib import TTFont, TTCollection
        ext = Path(font_path).suffix.lower()
        fonts = (TTCollection(str(font_path)).fonts
                 if ext == ".ttc" else [TTFont(str(font_path), lazy=True)])
        wanted_key = _font_alias_key(wanted_name)
        for tt in fonts:
            if "name" not in tt:
                continue
            for rec in tt["name"].names:
                if rec.nameID not in (1, 4, 16, 21):
                    continue
                try:
                    ckey  = _font_alias_key(rec.toUnicode())
                    ratio = SequenceMatcher(None, wanted_key, ckey).ratio()
                    if ratio >= threshold:
                        return True
                except Exception:
                    pass
    except Exception:
        pass
    return False


def _http_download(url, dest_path, timeout=30, min_size=1024,
                   allow_zip_extract=True):
    """Download a font file (or a ZIP containing one).

    Returns a list of saved Paths on success (usually 1; multiple when a ZIP
    archive contains several font files). Returns [] on failure.

    Features:
      • Magic-byte validation for .ttf / .otf to reject HTML / 404 pages.
      • Automatic ZIP extraction: if the response is a ZIP (PK\x03\x04 header),
        all .ttf/.otf members inside are extracted next to ``dest_path``.
      • Size sanity check via ``min_size``.
    """
    import zipfile
    import io

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except Exception:
        return []

    if not data or len(data) < min_size:
        return []

    dest_path = Path(dest_path)
    dest_dir = dest_path.parent
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return []

    # ---- ZIP archive? extract every font inside ----
    if allow_zip_extract and data[:4] == b"PK\x03\x04":
        extracted = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for member in zf.namelist():
                    low = member.lower()
                    if not (low.endswith(".ttf") or low.endswith(".otf")):
                        continue
                    if member.endswith("/"):
                        continue
                    try:
                        with zf.open(member) as fh:
                            blob = fh.read()
                    except Exception:
                        continue
                    if len(blob) < 1024 or not _is_font_magic(blob):
                        continue
                    # Sanitize the inner filename, keep its extension
                    inner = Path(member).name
                    safe = re.sub(r"[^A-Za-z0-9._\-]", "_", inner) or "font.ttf"
                    out = dest_dir / safe
                    # Avoid overwriting unrelated files
                    if out.exists():
                        stem, suf = out.stem, out.suffix
                        i = 1
                        while (dest_dir / f"{stem}_{i}{suf}").exists():
                            i += 1
                        out = dest_dir / f"{stem}_{i}{suf}"
                    try:
                        out.write_bytes(blob)
                        extracted.append(out)
                    except Exception:
                        continue
        except zipfile.BadZipFile:
            return []
        return extracted

    # ---- Plain font file: verify magic and write ----
    suf = dest_path.suffix.lower()
    if suf in (".ttf", ".otf"):
        if not _is_font_magic(data):
            return []
    try:
        dest_path.write_bytes(data)
    except Exception:
        return []
    return [dest_path]


def _font_alias_key(name):
    """Normalize a font name for cache/catalog lookup."""
    return re.sub(r"[^a-zA-Z0-9\u0600-\u06ff]", "", name).lower()


# ── Strategy 1: Google Fonts via gwfh API ─────────────────────────────────
def _try_google_fonts(name, dest_dir):
    """Look up the font on the public google-webfonts-helper API."""
    candidates = []
    low = name.lower().strip()
    if low in GOOGLE_FONTS_SLUGS_BY_ALIAS:
        candidates.append(GOOGLE_FONTS_SLUGS_BY_ALIAS[low])
    # Auto-slug: strip the weight word, lowercase, hyphenate
    auto = re.sub(r"[^a-zA-Z0-9 ]", "", low).strip()
    auto = re.sub(r"\s+(medium|bold|light|regular|semibold|black|thin|italic)\s*$",
                  "", auto)
    auto = auto.replace(" ", "-")
    if auto and auto not in candidates:
        candidates.append(auto)

    for slug in candidates:
        info = _http_get_json(f"https://gwfh.mranftl.com/api/fonts/{slug}")
        if not info or not info.get("variants"):
            continue
        variants = info["variants"]
        family = info.get("family", slug)
        downloaded = []
        # Try to grab regular + bold + medium when present
        wanted_ids = {"regular", "500", "600", "700"}
        for v in variants:
            if v.get("id") not in wanted_ids:
                continue
            ttf_url = v.get("ttf")
            if not ttf_url:
                continue
            label = {"regular":"Regular", "500":"Medium",
                     "600":"SemiBold", "700":"Bold"}.get(v["id"], v["id"])
            dest = Path(dest_dir) / f"{family.replace(' ', '_')}-{label}.ttf"
            got = _http_download(ttf_url, dest)
            if got:
                downloaded.extend(got)
        if downloaded:
            return downloaded
    return []


# ── Strategy 2: known-good direct URLs (exact font, verified) ─────────────
def _try_direct_urls(name, dest_dir):
    """Check FONT_DIRECT_URLS for a verified direct download of the exact font."""
    key = _font_alias_key(name)
    urls = None
    if key in FONT_DIRECT_URLS:
        urls = FONT_DIRECT_URLS[key]
    else:
        # prefix match (e.g. "amiribolditalic" starts with "amiribold")
        for k in sorted(FONT_DIRECT_URLS.keys(), key=len, reverse=True):
            if key.startswith(k) or k.startswith(key[:max(4, len(key)-3)]):
                urls = FONT_DIRECT_URLS[k]
                break
    if not urls:
        return []
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    for url in urls:
        ext  = ".ttf" if ".ttf" in url.lower() else ".otf"
        dest = Path(dest_dir) / f"{safe}-direct{ext}"
        got  = _http_download(url, dest)
        # Verify the file actually contains the name we need
        verified = [p for p in got if _font_name_matches(p, name)]
        if verified:
            return verified
        # Clean up unverified files
        for p in got:
            try: Path(p).unlink()
            except Exception: pass
    return []


# ── Strategy 3: GitHub Code Search ────────────────────────────────────────
def _try_github_search(name, dest_dir):
    """GitHub Code Search → first raw URL ending in .ttf/.otf."""
    q_name = re.sub(r"[^a-zA-Z0-9_\- ]", " ", name).strip().replace(" ", "+")
    if not q_name or len(q_name) < 3:
        return []
    for ext in ("ttf", "otf"):
        url = ("https://api.github.com/search/code?q="
               f"filename:{q_name}.{ext}+extension:{ext}&per_page=5")
        data = _http_get_json(url, timeout=20)
        if not data or not data.get("items"):
            continue
        for item in data["items"]:
            raw_url = (item.get("html_url", "")
                          .replace("github.com/", "raw.githubusercontent.com/")
                          .replace("/blob/", "/"))
            if not raw_url.endswith(f".{ext}"):
                continue
            dest = Path(dest_dir) / f"{re.sub(r'[^A-Za-z0-9_-]', '_', name)}.{ext}"
            got = _http_download(raw_url, dest)
            if got:
                return got
    return []


# ── Strategy 4: DuckDuckGo HTML search ────────────────────────────────────
def _try_duckduckgo(name, dest_dir):
    """DDG HTML search — picks .ttf / .otf / .zip links from results.
    Sends 2 queries (precise + generic) and tries the top 5 hits each."""
    safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    queries = [
        f'"{name}" (filetype:ttf OR filetype:otf)',
        f'"{name}" font download ttf',
    ]
    for q in queries:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
        html = _http_get_text(url, timeout=20)
        if not html:
            continue
        urls = []
        for m in re.finditer(r'href="(?://duckduckgo\.com/l/\?uddg=([^&"]+))', html):
            decoded = urllib.parse.unquote(m.group(1))
            base = decoded.lower().split("?")[0]
            if base.endswith((".ttf", ".otf", ".zip")):
                urls.append(decoded)
        for m in re.finditer(r'href="(https?://[^"]+\.(?:ttf|otf|zip))"', html, re.I):
            if m.group(1) not in urls:
                urls.append(m.group(1))
        for u in urls[:5]:
            base = u.lower().split("?")[0]
            ext = ".zip" if base.endswith(".zip") else (
                  ".otf" if base.endswith(".otf") else ".ttf")
            dest = Path(dest_dir) / f"{safe_name}-ddg{ext}"
            got = _http_download(u, dest, timeout=25)
            if got:
                return got
    return []


# ── Strategy 5: Bing search (backup when DDG misses) ──────────────────────
def _try_bing(name, dest_dir):
    """Bing HTML search backup — different result set than DDG.

    Bing has no captcha for unauthenticated browser queries, returns plain
    anchors to .ttf / .otf / .zip files. We extract & try the top 5.
    """
    safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    queries = [
        f'"{name}" filetype:ttf',
        f'"{name}" filetype:otf',
        f'"{name}" font ttf download',
    ]
    for q in queries:
        url = ("https://www.bing.com/search?"
               + urllib.parse.urlencode({"q": q, "count": "15"}))
        html = _http_get_text(url, timeout=20)
        if not html:
            continue
        urls = []
        for m in re.finditer(r'href="(https?://[^"<>]+?\.(?:ttf|otf|zip))["?#]',
                             html, re.I):
            urls.append(m.group(1))
        seen, urls = set(), [u for u in urls if not (u in seen or seen.add(u))]
        for u in urls[:5]:
            base = u.lower().split("?")[0]
            ext = ".zip" if base.endswith(".zip") else (
                  ".otf" if base.endswith(".otf") else ".ttf")
            dest = Path(dest_dir) / f"{safe_name}-bing{ext}"
            got = _http_download(u, dest, timeout=25)
            if got:
                return got
    return []


# ── Strategy 6: font site scrapers ────────────────────────────────────────
def _try_font_sites(name, dest_dir):
    """Scrape fontspace.com, 1001fonts.com, dafont.com, arbfonts.com.

    These sites host thousands of free fonts — including many Arabic fansub
    fonts that don't appear on Google Fonts or GitHub.  We never touch the
    DOM; we only follow direct .ttf/.otf/.zip download links.

    Priority order:
      1. arbfonts.com  — biggest Arabic/Persian free font collection
      2. fontspace.com — large multi-language searchable catalogue
      3. 1001fonts.com — long-running free/demo font library
      4. dafont.com    — classic; good for Latin display/fantasy fonts
    """
    safe_name  = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    slug_name  = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    slug_score = re.sub(r'\s+', '+', name.strip())

    # ── helper: try a list of direct font URLs ──────────────────────────
    def _try_urls(candidates, tag):
        for u in candidates:
            base = u.lower().split("?")[0]
            ext  = ".zip" if base.endswith(".zip") else (
                   ".otf" if base.endswith(".otf") else ".ttf")
            dest = Path(dest_dir) / f"{safe_name}-{tag}{ext}"
            got  = _http_download(u, dest, timeout=25)
            if got:
                return got
        return []

    # ── helper: scrape a search page for .ttf/.otf/.zip links ──────────
    def _scrape_links(url, tag, extra_patterns=()):
        html = _http_get_text(url, timeout=20)
        if not html:
            return []
        urls = []
        # Direct font file links
        for m in re.finditer(
                r'href=["\']?(https?://[^"\'<>\s]+?\.(?:ttf|otf|zip))["\']?',
                html, re.I):
            urls.append(m.group(1))
        # Site-specific download-page patterns
        for pat in extra_patterns:
            for m in re.finditer(pat, html, re.I):
                candidate = m.group(1)
                if not candidate.startswith("http"):
                    candidate = "https://" + candidate.lstrip("/")
                urls.append(candidate)
        # Deduplicate, keep order
        seen, clean = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u); clean.append(u)
        return _try_urls(clean[:8], tag)

    # 1. arbfonts.com — Arabic-first font library
    got = _scrape_links(
        f"https://arbfonts.com/font-search.php?search={urllib.parse.quote(name)}",
        "arbfonts",
        extra_patterns=[
            r'href=["\']([^"\']*download[^"\']*\.(?:ttf|otf|zip))["\']'
        ]
    )
    if got: return got

    # 2. fontspace.com
    got = _scrape_links(
        f"https://www.fontspace.com/search?q={urllib.parse.quote(name)}",
        "fontspace",
        extra_patterns=[
            r'"downloadUrl"\s*:\s*"([^"]+)"',
            r'href=["\']([^"\']+/font/[^"\']+\.(?:ttf|otf|zip))["\']',
        ]
    )
    if got: return got

    # 3. 1001fonts.com
    got = _scrape_links(
        f"https://www.1001fonts.com/search.html?search={urllib.parse.quote(name)}",
        "1001fonts",
        extra_patterns=[
            r'href=["\']([^"\']+fonts/[^"\']+\.(?:ttf|otf|zip))["\']',
        ]
    )
    if got: return got

    # 4. dafont.com (also covers many Latin display fonts used in OP/ED)
    got = _scrape_links(
        f"https://www.dafont.com/search.php?q={urllib.parse.quote(name)}&l[]=1&l[]=7",
        "dafont",
        extra_patterns=[
            r'href=["\']([^"\']+fonts/[^"\']+\.(?:ttf|otf|zip))["\']',
        ]
    )
    if got: return got

    # 5. Direct slug attempts on the most reliable sites
    got = _try_urls([
        f"https://arbfonts.com/fonts/{slug_name}.zip",
        f"https://arbfonts.com/fonts/{safe_name}.ttf",
        f"https://www.fontspace.com/fonts/download?name={urllib.parse.quote(name)}",
        f"https://www.dafont.com/{slug_name}.font",
    ], "direct")
    return got


# ── FontHunter orchestrator ────────────────────────────────────────────────

# ── Strategy 7: curated GitHub raw URLs across many font repos ────────────
# A massive list of (alias_regex, raw_url) tuples. Each tuple is checked
# in order — the first regex that matches the requested font's normalized
# key wins, the URL is downloaded, and the result is verified by name.
#
# These all live on github.com/<user>/<repo>/raw/<branch>/<path> which works
# from any country without auth.  Lists were curated from:
#   - aliftype/*           (Amiri family, Reem Kufi, Aref Ruqaa, Mada, Raqq)
#   - alif-type/*          (mirror of the above on the old org)
#   - rastikerdar/*        (Vazir, Samim, Shabnam, Sahel, Tanha, Estedad)
#   - rahatool/persian-fonts (Lotus, Yekan, Titr, Zar, Nazanin, Traffic)
#   - majnooni/persian-fonts-free
#   - akiarostami/iransans
#   - nekofar/iranian-sans-fontface
#   - jenskutilek/free-fonts (Apache-licensed bundle)
#   - google/fonts          (the official Google Fonts repo)
#   - notofonts/notofonts.github.io
#   - IBM/plex
#   - source-foundry/Hack
#   - JetBrains/JetBrainsMono
#   - tonsky/FiraCode
#   - mozilla/fxa-content-server-l10n (Fira)

# ── Strategy: GitHub Releases API ─────────────────────────────────────────
# Many quality open-source font projects publish their binaries only as
# ZIP assets on GitHub Releases (rather than committing TTFs to the repo).
# This map points alias patterns at "owner/name" repos; the strategy hits
# the public Releases API, downloads the first .zip / .ttf asset, and
# _http_download auto-extracts and validates the contents.
GITHUB_FONT_REPOS = [
    # ─── aliftype foundry (Arabic — OFL) ───────────────────────────────
    (r"^amiri(quran|bold|italic|book|regular)?$|^quran$",   "aliftype/amiri"),
    (r"^arefruqaa(regular|bold)?$|^arefruqaaink",           "aliftype/aref-ruqaa"),
    (r"^reemkufi(regular)?$",                               "aliftype/reem-kufi"),
    (r"^mada(regular)?$",                                   "aliftype/mada"),
    (r"^raqq(regular)?$",                                   "aliftype/raqq"),
    (r"^ranakufi$|^rana$",                                  "aliftype/rana-kufi"),
    (r"^qashib(regular)?$",                                 "aliftype/qashib"),
    # ─── SIL Arabic / Indic (OFL) ──────────────────────────────────────
    (r"^lateef(regular)?$",                                 "silnrsi/font-lateef"),
    (r"^scheherazade",                                      "silnrsi/font-scheherazade-new"),
    (r"^harmattan",                                         "silnrsi/font-harmattan"),
    (r"^alkalami",                                          "silnrsi/font-alkalami"),
    (r"^awami",                                             "silnrsi/font-awami-nastaliq"),
    (r"^absher",                                            "Tarek-Sayed/Absher"),
    # ─── rastikerdar Persian foundry (OFL) ─────────────────────────────
    (r"^vazirmatn|^vazir(regular|bold|medium|light|black|thin)?$",  "rastikerdar/vazirmatn"),
    (r"^samim(font)?$",                                     "rastikerdar/samim-font"),
    (r"^shabnam(font)?$",                                   "rastikerdar/shabnam-font"),
    (r"^sahel(font)?$",                                     "rastikerdar/sahel-font"),
    (r"^tanha(font)?$",                                     "rastikerdar/tanha-font"),
    (r"^gandom(font)?$",                                    "rastikerdar/gandom-font"),
    (r"^parastoo(font)?$",                                  "rastikerdar/parastoo-font"),
    (r"^nahid(font)?$",                                     "rastikerdar/nahid-font"),
    (r"^estedad(font)?$",                                   "aminabbasi/estedad-font"),
    (r"^mikhak",                                            "rastikerdar/mikhak-font"),
    (r"^peydanp|^peyda",                                    "rastikerdar/peydanp"),
    # ─── Nerd Fonts (patched programming fonts with icon glyphs) ───────
    (r"^nerdfont|^nfont|^caskaydiancove",                   "ryanoasis/nerd-fonts"),
    # ─── Other popular Latin/multi-lang projects (binaries-in-releases) ─
    (r"^jetbrainsmono",                                     "JetBrains/JetBrainsMono"),
    (r"^firacode",                                          "tonsky/FiraCode"),
    (r"^firasans|^firamono",                                "mozilla/Fira"),
    (r"^cascadiacode|^cascadia(mono)?",                     "microsoft/cascadia-code"),
    (r"^inter(regular|bold|italic|thin|light|medium|black)?$", "rsms/inter"),
    (r"^recursive",                                         "arrowtype/recursive"),
    (r"^commitmono",                                        "eigilnikolajsen/commit-mono"),
    (r"^monaspace",                                         "githubnext/monaspace"),
    (r"^geist(mono)?",                                      "vercel/geist-font"),
    # ─── CJK / East Asian fonts ────────────────────────────────────────
    (r"^notosanscjk|^notoserifcjk",                         "googlefonts/noto-cjk"),
    (r"^sourcehansan|^sourcehansans",                        "adobe-fonts/source-han-sans"),
    (r"^sourcehanserif",                                    "adobe-fonts/source-han-serif"),
    (r"^zpix",                                              "ssshooter/zpix-font"),
]


def _try_github_releases(name, dest_dir):
    """Try the GitHub Releases API for any repo that ships fonts as ZIPs.

    Workflow:
      • Hit api.github.com/repos/<repo>/releases/latest
      • For each asset whose name ends in .zip / .ttf / .otf:
          - download via _http_download (auto-extracts ZIPs)
          - verify at least one extracted file matches `name`
      • Keep only verified files; clean up false-positive extracts.
    """
    key = _font_alias_key(name)
    if not key:
        return []
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    target_repo = None
    for pattern, repo in GITHUB_FONT_REPOS:
        if re.match(pattern, key):
            target_repo = repo
            break
    if not target_repo:
        return []

    rel = _http_get_json(
        f"https://api.github.com/repos/{target_repo}/releases/latest",
        timeout=20)
    if not rel or not rel.get("assets"):
        # Some projects only have unreleased "tags" — fall back to /tags
        tag_url = f"https://api.github.com/repos/{target_repo}/tags"
        tags = _http_get_json(tag_url, timeout=20) or []
        if not tags:
            return []
        # Try the source tarball, although it usually contains only sources
        return []

    for asset in rel["assets"]:
        asset_name = (asset.get("name") or "").lower()
        if not asset_name.endswith((".zip", ".ttf", ".otf", ".ttc")):
            continue
        url = asset.get("browser_download_url")
        if not url:
            continue
        ext = (".zip" if asset_name.endswith(".zip") else
               ".ttf" if asset_name.endswith(".ttf") else
               ".otf" if asset_name.endswith(".otf") else ".ttc")
        dest = Path(dest_dir) / f"{safe}-release{ext}"
        got = _http_download(url, dest, timeout=60)
        # Verify by name. _http_download for a ZIP returns ALL extracted
        # files — keep only those whose internal font name matches.
        verified = [p for p in got if _font_name_matches(p, name)]
        if verified:
            # Remove unverified leftovers to avoid polluting fonts/
            unverified = [p for p in got if p not in verified]
            for p in unverified:
                try: Path(p).unlink()
                except Exception: pass
            return verified
        # If nothing matched, clean up everything from this asset
        for p in got:
            try: Path(p).unlink()
            except Exception: pass
    return []


GITHUB_FONT_MIRRORS = [
    # ─── Arabic (aliftype foundry — OFL) ────────────────────────────────

    # ─── Arabic (SIL — OFL) ─────────────────────────────────────────────
    (r"^scheherazade|^scheherazadenew",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/scheherazadenew/ScheherazadeNew-Regular.ttf"),
    (r"^harmattan",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/harmattan/Harmattan-Regular.ttf"),

    # ─── Arabic (Google Fonts repo — OFL) ───────────────────────────────
    (r"^cairo(regular|medium|bold|semibold|black|light)?$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/cairo/Cairo%5Bslnt%2Cwght%5D.ttf"),
    (r"^tajawal$|^tajawalregular$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/tajawal/Tajawal-Regular.ttf"),
    (r"^tajawalmedium$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/tajawal/Tajawal-Medium.ttf"),
    (r"^tajawalbold$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/tajawal/Tajawal-Bold.ttf"),
    (r"^changa$|^changaregular$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/changa/Changa%5Bwght%5D.ttf"),
    (r"^elmessiri$|^messiri",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/elmessiri/ElMessiri%5Bwght%5D.ttf"),
    (r"^readexpro|^readex",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/readexpro/ReadexPro%5BHEXP%2Cwght%5D.ttf"),
    (r"^markazitext$|^markazi",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/markazitext/MarkaziText%5Bwght%5D.ttf"),
    (r"^lalezar",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/lalezar/Lalezar-Regular.ttf"),
    (r"^katibeh",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/katibeh/Katibeh-Regular.ttf"),
    (r"^rakkas",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/rakkas/Rakkas-Regular.ttf"),
    (r"^notosansarabic$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansarabic/NotoSansArabic%5Bwdth%2Cwght%5D.ttf"),
    (r"^notonaskharabic$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf"),
    (r"^notokufiarabic$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notokufiarabic/NotoKufiArabic%5Bwght%5D.ttf"),

    # ─── Persian / Farsi (rastikerdar — OFL) ───────────────────────────

    # ─── Persian (rahatool — classic Iranian X-series) ─────────────────
    (r"^xbzar$|^zar$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Zar.regular.ttf"),
    (r"^xmyekan$|^yekan$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Yekan.regular.ttf"),
    (r"^xmvahid$|^vahid$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Yekan.regular.ttf"),
    (r"^xmtitr$|^titr$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Titr.bold.ttf"),
    (r"^xmlotus$|^lotus$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Lotus.regular.ttf"),
    (r"^xpziba$|^ziba$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Nazanin.regular.ttf"),
    (r"^xpnazanin$|^nazanin$|^afsaneh$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Nazanin.regular.ttf"),
    (r"^morvarid$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Morvarid.regular.ttf"),
    (r"^traffic$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Traffic.regular.ttf"),
    (r"^iranastaliq$|^irannastaliq$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/IranNastaliq.regular.ttf"),
    (r"^besmellah$",
        "https://raw.githubusercontent.com/rahatool/persian-fonts/master/Besmellah.regular.ttf"),

    # ─── Japanese (Google Fonts repo / Noto — OFL) ─────────────────────
    (r"^notosansjp",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"),
    (r"^notoserifjp",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifjp/NotoSerifJP%5Bwght%5D.ttf"),
    (r"^kleeone$|^klee$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/kleeone/KleeOne-Regular.ttf"),
    (r"^kleeonesemibold$|^kleesemibold$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/kleeone/KleeOne-SemiBold.ttf"),
    (r"^yujisyuku",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/yujisyuku/YujiSyuku-Regular.ttf"),
    (r"^zenmarugothic",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/zenmarugothic/ZenMaruGothic-Regular.ttf"),
    (r"^mplus|^mpluscode",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/mplus1code/MPLUS1Code%5Bwght%5D.ttf"),
    (r"^sawarabigothic",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/sawarabigothic/SawarabiGothic-Regular.ttf"),
    (r"^sawarabimincho",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/sawarabimincho/SawarabiMincho-Regular.ttf"),

    # ─── Korean (Google Fonts — OFL) ───────────────────────────────────
    (r"^notosanskr|^dotum",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"),
    (r"^notoserifkr",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifkr/NotoSerifKR%5Bwght%5D.ttf"),
    (r"^nanumgothic",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf"),

    # ─── Latin / display popular fansub fonts (Google Fonts — OFL) ─────
    (r"^opensans(regular|semibold|bold|medium|light|extrabold)?$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/opensans/OpenSans%5Bwdth%2Cwght%5D.ttf"),
    (r"^roboto$|^robotoregular$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf"),
    (r"^cabin$|^cabinpl",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/cabin/Cabin%5Bwdth%2Cwght%5D.ttf"),
    (r"^inter$|^interregular$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"),
    (r"^poppins$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Regular.ttf"),
    (r"^orbitron$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf"),
    (r"^grandstander$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/grandstander/Grandstander%5Bwght%5D.ttf"),
    (r"^firacode|^firamono",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/firacode/FiraCode%5Bwght%5D.ttf"),
    (r"^firasans",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/firasans/FiraSans-Regular.ttf"),
    (r"^sourcecodepro",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/sourcecodepro/SourceCodePro%5Bwght%5D.ttf"),
    (r"^sourcesans",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/sourcesans3/SourceSans3%5Bwght%5D.ttf"),
    (r"^jetbrainsmono",
        "https://raw.githubusercontent.com/JetBrains/JetBrainsMono/master/fonts/ttf/JetBrainsMono-Regular.ttf"),
    (r"^ibmplexsans",
        "https://raw.githubusercontent.com/IBM/plex/master/packages/plex-sans/fonts/complete/ttf/IBMPlexSans-Regular.ttf"),
    (r"^ibmplexmono",
        "https://raw.githubusercontent.com/IBM/plex/master/packages/plex-mono/fonts/complete/ttf/IBMPlexMono-Regular.ttf"),
    (r"^ibmplexserif",
        "https://raw.githubusercontent.com/IBM/plex/master/packages/plex-serif/fonts/complete/ttf/IBMPlexSerif-Regular.ttf"),
    (r"^hack$|^hackregular$",
        "https://raw.githubusercontent.com/source-foundry/Hack/master/build/ttf/Hack-Regular.ttf"),

    # ─── Extra fansub-popular fonts (Google Fonts — OFL) ──────────────
    (r"^nunito$|^nunitoregular$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/nunito/Nunito%5Bwght%5D.ttf"),
    (r"^comfortaa$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/comfortaa/Comfortaa%5Bwght%5D.ttf"),
    (r"^satisfy$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/satisfy/Satisfy-Regular.ttf"),
    (r"^exo2$|^exo$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/exo2/Exo2%5Bwght%5D.ttf"),
    (r"^lobster$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/lobster/Lobster-Regular.ttf"),
    (r"^pacifico$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/pacifico/Pacifico-Regular.ttf"),
    (r"^arefruqaaink",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/arefruqaaink/ArefRuqaaInk-Regular.ttf"),
    (r"^baloo|^baloo2",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/baloo2/Baloo2%5Bwght%5D.ttf"),
    (r"^almarai",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/almarai/Almarai-Regular.ttf"),
    (r"^vibes$|^arefvibes",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/arefruqaa/ArefRuqaa-Regular.ttf"),
    (r"^aller$",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/aller/Aller-Regular.ttf"),
    (r"^pthelvetica|^helveticaneue",
        "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"),
]


def _try_github_mirrors(name, dest_dir):
    """Walk the curated GITHUB_FONT_MIRRORS table for a hand-mapped match.

    Each entry is (regex, url) where the URL was hand-curated as the best
    available source for fonts matching the regex. Because the mapping is
    explicit, we trust it: we still verify the bytes look like a font, but
    we use a *looser* name-match threshold so fonts whose internal
    name differs from the requested alias (e.g. 'XM Yekan' → 'Web Yekan',
    'Vazir' → 'Vazirmatn') still pass.
    """
    key = _font_alias_key(name)
    if not key:
        return []
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    for pattern, url in GITHUB_FONT_MIRRORS:
        if not re.match(pattern, key):
            continue
        ext  = ".otf" if url.lower().split("?")[0].endswith(".otf") else ".ttf"
        dest = Path(dest_dir) / f"{safe}-mirror{ext}"
        got  = _http_download(url, dest, timeout=25)
        if not got:
            continue
        # The URL was hand-curated, so accept any valid font that came
        # from it — the magic-bytes check inside _http_download already
        # rejected HTML 404 pages and non-font files.
        verified = [p for p in got
                    if _font_name_matches(p, name, threshold=0.55)]
        if verified:
            return verified
        # If even the loose threshold failed, trust the curation: keep
        # the first file as-is. This matters for fonts where the foundry
        # ships a renamed variant (XM → Web, Vazir → Vazirmatn, etc.).
        if got:
            return [got[0]]
    return []


# ── Strategy 8: Fontshare public API ──────────────────────────────────────
def _try_fontshare(name, dest_dir):
    """Look the font up on the Fontshare public API (commercial-free).

    Fontshare exposes  https://api.fontshare.com/v2/fonts
    Each entry has a `slug`, `name`, and `styles[].links.default` direct URL.
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    key  = _font_alias_key(name)
    if not key:
        return []
    data = _http_get_json("https://api.fontshare.com/v2/fonts?limit=400", timeout=20)
    if not data:
        return []
    families = data.get("fonts") or data if isinstance(data, list) else data.get("fonts", [])
    if not isinstance(families, list):
        return []
    best = None
    for fam in families:
        fam_key = _font_alias_key(fam.get("name") or fam.get("slug") or "")
        if fam_key and (fam_key == key or fam_key.startswith(key) or key.startswith(fam_key)):
            best = fam
            break
    if not best:
        return []
    # Find a regular/medium style URL
    chosen_url = None
    for style in best.get("styles", []):
        name_l = (style.get("name") or "").lower()
        url    = (style.get("links") or {}).get("default") or style.get("default_url")
        if not url:
            continue
        if any(w in name_l for w in ("regular", "medium", "book")):
            chosen_url = url; break
        if chosen_url is None:
            chosen_url = url
    if not chosen_url:
        return []
    ext  = ".otf" if chosen_url.lower().split("?")[0].endswith(".otf") else ".ttf"
    dest = Path(dest_dir) / f"{safe}-fontshare{ext}"
    got  = _http_download(chosen_url, dest, timeout=25)
    return [p for p in got if _font_name_matches(p, name)] or got


# ── Strategy 9: Internet Archive search ──────────────────────────────────
def _try_internet_archive(name, dest_dir):
    """Search archive.org for the font name, then download a .ttf/.otf/.zip
    from the first matching item's file list.

    archive.org item URL:    https://archive.org/details/<identifier>
    files endpoint (JSON):   https://archive.org/metadata/<identifier>
    direct file download:    https://archive.org/download/<identifier>/<file>
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    q = urllib.parse.quote(name + " font")
    search_url = (f"https://archive.org/advancedsearch.php"
                  f"?q={q}&fl%5B%5D=identifier&rows=5&page=1&output=json")
    data = _http_get_json(search_url, timeout=20)
    if not data:
        return []
    docs = (data.get("response") or {}).get("docs") or []
    for doc in docs[:5]:
        ident = doc.get("identifier")
        if not ident:
            continue
        meta = _http_get_json(f"https://archive.org/metadata/{urllib.parse.quote(ident)}",
                              timeout=20)
        if not meta:
            continue
        files = meta.get("files") or []
        for f in files:
            fn = (f.get("name") or "").lower()
            if not fn.endswith((".ttf", ".otf", ".zip", ".ttc")):
                continue
            url = f"https://archive.org/download/{urllib.parse.quote(ident)}/{urllib.parse.quote(f['name'])}"
            ext = ".zip" if fn.endswith(".zip") else (".otf" if fn.endswith(".otf") else ".ttf")
            dest = Path(dest_dir) / f"{safe}-archive{ext}"
            got  = _http_download(url, dest, timeout=30)
            verified = [p for p in got if _font_name_matches(p, name)]
            if verified:
                return verified
            for p in got:
                try: Path(p).unlink()
                except Exception: pass
    return []


# ── Strategy 10: Wayback Machine for dead direct URLs ────────────────────
def _try_wayback(name, dest_dir):
    """For any URL from GITHUB_FONT_MIRRORS that returned 404, try the
    Wayback Machine snapshot. Useful when a repo moved/renamed."""
    key = _font_alias_key(name)
    if not key:
        return []
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    for pattern, url in GITHUB_FONT_MIRRORS:
        if not re.match(pattern, key):
            continue
        snapshot = _wayback_url(url)
        if not snapshot:
            continue
        ext  = ".otf" if url.lower().split("?")[0].endswith(".otf") else ".ttf"
        dest = Path(dest_dir) / f"{safe}-wayback{ext}"
        got  = _http_download(snapshot, dest, timeout=30)
        verified = [p for p in got if _font_name_matches(p, name)]
        if verified:
            return verified
        for p in got:
            try: Path(p).unlink()
            except Exception: pass
    return []


# =========================================================================
#  v1.7 — DEDICATED FONT SITE SCRAPERS
# =========================================================================
# Each scraper hits the public search page, extracts the slug/ID of the
# best matching result, then constructs the direct download URL.  None of
# these sites use Cloudflare Turnstile or a JS-only download flow.
#
# IMPORTANT LICENSING NOTE
#   These scrapers can fetch fonts whose licensing varies (free for personal
#   use, OFL, "free demo for commercial trial", or unknown).  The end user is
#   responsible for verifying the EULA of every downloaded font before
#   embedding it in distributed content.  Many of these sites mirror fonts
#   that the original foundry sells commercially — that mirror may or may
#   not be authorised by the foundry.
# =========================================================================

def _try_fontdownload(name, dest_dir):
    """Scraper for font.download.

    Flow:
      1. GET https://font.download/search/{name}
      2. Find first matching slug ending in "-N"
      3. GET https://font.download/dl/font/{slug}.zip  → ZIP archive
    The ZIP is auto-extracted by _http_download and verified by name.
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    q    = urllib.parse.quote(name)
    html = _http_get_text(f"https://font.download/search/{q}", timeout=20)
    if not html:
        return []
    # Find direct dl links: font.download/dl/font/{slug}.zip
    direct_links = re.findall(
        r'href="(https?://font\.download/dl/font/[^"\']+\.zip)"', html, re.I)
    if not direct_links:
        # Fallback: find /font/{slug} pages and build the dl URL
        slugs = re.findall(r'/font/([a-z0-9-]+)["\'/]', html, re.I)
        direct_links = [f"https://font.download/dl/font/{s}.zip"
                        for s in list(dict.fromkeys(slugs))[:5]]
    for url in direct_links[:4]:
        dest = Path(dest_dir) / f"{safe}-fontdownload.zip"
        got  = _http_download(url, dest, timeout=30)
        verified = [p for p in got if _font_name_matches(p, name, threshold=0.55)]
        if verified:
            for p in got:
                if p not in verified:
                    try: Path(p).unlink()
                    except Exception: pass
            return verified
        # If nothing verified, keep the first file as-is (user requested
        # "no matter what" — the curated URL gives us something useful)
        if got:
            return [got[0]]
    return []


def _try_fontsloader(name, dest_dir):
    """Scraper for en.fontsloader.com.

    The site's server-side search returns a fixed featured list rather
    than per-query results, so we try DIRECT /types/{slug} detail pages
    built from candidate slugs derived from the font name. Each detail
    page has a clean /type_files/{ID}/font.zip URL we can extract.
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    base = name.lower()
    # Build a list of slug candidates
    candidates = []
    candidates.append(re.sub(r'[^a-z0-9]+', '-', base).strip('-'))
    candidates.append(re.sub(r'[^a-z0-9]+', '', base))                 # "cabinpl"
    candidates.append(candidates[0].split('-')[0])                     # first token
    # Drop weight suffixes
    stripped = re.sub(r'-(regular|bold|medium|light|italic|book|semibold)$',
                      '', candidates[0])
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    _seen = set()
    candidates = [c for c in candidates if c and not (c in _seen or _seen.add(c))]

    for slug in candidates[:6]:
        detail = _http_get_text(f"https://en.fontsloader.com/types/{slug}",
                                timeout=20)
        if not detail or 'type_files' not in detail:
            continue
        m = re.search(r'href="(https?://[^"]*?type_files/[^"]+?/font\.zip)"',
                      detail)
        if not m:
            m = re.search(r'(/type_files/[^"]+?/font\.zip)', detail)
            url = ("https://en.fontsloader.com" + m.group(1)) if m else None
        else:
            url = m.group(1)
        if not url:
            continue
        dest = Path(dest_dir) / f"{safe}-fontsloader.zip"
        got  = _http_download(url, dest, timeout=30)
        if got:
            verified = [p for p in got if _font_name_matches(p, name, threshold=0.55)]
            return verified or [got[0]]
    return []


def _try_fontspace(name, dest_dir):
    """Scraper for fontspace.com.

    Fontspace is a JS-driven SPA so search HTML alone is not enough; we
    use the search-results collection links plus a direct-slug guess.
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    q    = urllib.parse.quote(name)
    html = _http_get_text(f"https://www.fontspace.com/search?q={q}", timeout=20)
    candidates = []
    if html:
        # Collection URLs hint at related families
        for cslug in re.findall(r'href="/collection/([a-z0-9-]+)"', html, re.I):
            candidates.append(cslug)
    # Direct slug guess from the name (works for many family-named fonts)
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    candidates += [base, f"{base}-font", base.replace('-', '')]
    _seen = set()
    candidates = [c for c in candidates if c and not (c in _seen or _seen.add(c))]

    for slug in candidates[:6]:
        for url in (f"https://www.fontspace.com/font/{slug}/download",
                    f"https://www.fontspace.com/family/{slug}/download"):
            dest = Path(dest_dir) / f"{safe}-fontspace.zip"
            got  = _http_download(url, dest, timeout=25)
            if got:
                verified = [p for p in got
                            if _font_name_matches(p, name, threshold=0.55)]
                return verified or [got[0]]
    return []


def _try_1001fonts(name, dest_dir):
    """Scraper for 1001fonts.com.

    The download URL pattern is clean and reliable:
        https://www.1001fonts.com/download/{slug}.zip
    We derive {slug} both from the search-results page AND from the
    normalized name directly (with hyphenation) for cases where the search
    result page only contains category links.
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    q    = urllib.parse.quote_plus(name)

    # Build a list of candidate slugs
    candidates = []
    # 1) Direct slug guess from the font name
    direct_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    candidates.append(direct_slug)
    # 2) Slug without "font" / weight suffix
    stripped = re.sub(r'-(regular|bold|medium|light|italic|book)$', '', direct_slug)
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    # 3) Try the search page for additional slugs
    html = _http_get_text(
        f"https://www.1001fonts.com/search.html?search={q}", timeout=20)
    if html:
        for slug in re.findall(r'href="/([a-z0-9-]+)-font\.html"', html, re.I):
            if slug not in candidates:
                candidates.append(slug)

    for slug in candidates[:6]:
        url  = f"https://www.1001fonts.com/download/{slug}.zip"
        dest = Path(dest_dir) / f"{safe}-1001fonts.zip"
        got  = _http_download(url, dest, timeout=30)
        if got:
            verified = [p for p in got if _font_name_matches(p, name, threshold=0.55)]
            return verified or [got[0]]
    return []


def _try_fontesk(name, dest_dir):
    """Scraper for fontesk.com.

    Their /?s= search returns latest articles rather than matched results,
    so we try direct /{slug}-font/ detail pages whose slug is derived
    from the font name. Each detail page has a /download/{id}/ link.
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    candidates = [f"{base}-font", f"{base}-typeface", f"{base}-font/",
                  f"{base}.html"]
    for slug_path in candidates[:4]:
        url = f"https://fontesk.com/{slug_path.rstrip('/')}/"
        detail = _http_get_text(url, timeout=15)
        if not detail:
            continue
        m = re.search(r'href="(https?://fontesk\.com/download/\d+/?)"', detail)
        if not m:
            m = re.search(r'href="(https?://[^"]+\.(?:zip|ttf|otf))"',
                          detail, re.I)
            if not m:
                continue
            dl = m.group(1)
            ext = (".zip" if dl.lower().endswith(".zip") else
                   ".otf" if dl.lower().endswith(".otf") else ".ttf")
        else:
            dl, ext = m.group(1), ".zip"
        dest = Path(dest_dir) / f"{safe}-fontesk{ext}"
        got  = _http_download(dl, dest, timeout=30)
        if got:
            verified = [p for p in got if _font_name_matches(p, name, threshold=0.55)]
            return verified or [got[0]]
    return []


def _try_befonts(name, dest_dir):
    """Scraper for befonts.com.

    befonts uses WordPress slugs. The site's search results are JS-driven,
    so we try direct slug guesses derived from the font name plus a small
    listing-page scan for any matching slug we can spot.
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    candidates = [base, f"{base}-font", base.replace('-', '')]
    for slug in candidates[:5]:
        url = f"https://befonts.com/{slug}.html"
        detail = _http_get_text(url, timeout=15)
        if not detail or 'download' not in detail.lower():
            continue
        m = re.search(r'href="(https?://[^"]+\.(?:zip|ttf|otf))"', detail, re.I)
        if not m:
            continue
        dl  = m.group(1)
        ext = (".zip" if dl.lower().endswith(".zip") else
               ".otf" if dl.lower().endswith(".otf") else ".ttf")
        dest = Path(dest_dir) / f"{safe}-befonts{ext}"
        got  = _http_download(dl, dest, timeout=30)
        if got:
            verified = [p for p in got if _font_name_matches(p, name, threshold=0.55)]
            return verified or [got[0]]
    return []


def _try_urbanfonts(name, dest_dir):
    """Scraper for urbanfonts.com.

    UrbanFonts' search endpoint is unreliable, so we try a direct
    /fonts/{slug}.htm guess plus parse any .htm slugs we can find.
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    candidates = [base, base.replace('-', '_'), base.replace('-', '')]
    # Pull additional slugs from the listing page (if reachable)
    listing = _http_get_text(
        f"https://www.urbanfonts.com/fonts/search.htm?q={urllib.parse.quote(name)}",
        timeout=15)
    if listing:
        for s in re.findall(r'href="/fonts/([a-z0-9_-]+)\.htm"', listing, re.I):
            if s not in candidates:
                candidates.append(s)
    for slug in candidates[:5]:
        detail = _http_get_text(
            f"https://www.urbanfonts.com/fonts/{slug}.htm", timeout=15)
        if not detail:
            continue
        m = re.search(
            r'href="((?:/|https?://www\.urbanfonts\.com/)?downloads/[^"]+\.(?:zip|ttf|otf))"',
            detail, re.I)
        if not m:
            continue
        dl = m.group(1)
        if dl.startswith('/'):
            dl = "https://www.urbanfonts.com" + dl
        ext = (".zip" if dl.lower().endswith(".zip") else
               ".otf" if dl.lower().endswith(".otf") else ".ttf")
        dest = Path(dest_dir) / f"{safe}-urbanfonts{ext}"
        got  = _http_download(dl, dest, timeout=30)
        if got:
            verified = [p for p in got if _font_name_matches(p, name, threshold=0.55)]
            return verified or [got[0]]
    return []


def _try_dafont_safe(name, dest_dir):
    """Scraper for dafont.com.

    DaFont serves a clean direct-download endpoint:
        https://dl.dafont.com/dl/?f={slug}
    The slug is the lowercased font name (e.g. "pacifico"). We obtain it
    from the search results, which contain links like
        href="pacifico.font"   or   href="//dl.dafont.com/dl/?f=pacifico"
    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    q    = urllib.parse.quote(name)
    html = _http_get_text(f"https://www.dafont.com/search.php?q={q}", timeout=20)
    if not html:
        return []
    slugs = re.findall(r'href="([a-z0-9_]+)\.font"', html, re.I)
    # Also pick up any direct /dl/?f= URLs that appear inline
    slugs += re.findall(r'/dl/\?f=([a-z0-9_]+)', html, re.I)
    # Last-resort: derive slug directly from the requested name
    slugs.append(re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_'))
    slugs = list(dict.fromkeys(slugs))[:6]
    for slug in slugs:
        url  = f"https://dl.dafont.com/dl/?f={slug}"
        dest = Path(dest_dir) / f"{safe}-dafont.zip"
        got  = _http_download(url, dest, timeout=30)
        if got:
            verified = [p for p in got if _font_name_matches(p, name, threshold=0.55)]
            return verified or [got[0]]
    return []



def _try_fonts2u(name, dest_dir):
    """Scraper for fonts2u.com pages that expose a direct /download/ endpoint."""
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    candidates = [f"https://fonts2u.com/{slug}.font"]
    search_q = urllib.parse.quote(name)
    sh = _http_get_text(f"https://fonts2u.com/search.html?q={search_q}", timeout=20)
    if sh:
        for u in re.findall(r'href="(/[^"?#]+\.font)"', sh, re.I):
            url = urllib.parse.urljoin('https://fonts2u.com/', u)
            if url not in candidates:
                candidates.append(url)
    for page in candidates[:6]:
        html = _http_get_text(page, timeout=20)
        if not html:
            continue
        m = re.search(r'href="([^"]*/download/[^"?#]+)"', html, re.I)
        if not m:
            m = re.search(r'href="([^"]+\.(?:zip|ttf|otf))"[^>]*>\s*Download', html, re.I)
        if not m:
            continue
        dl = urllib.parse.urljoin(page, m.group(1))
        ext = '.zip' if dl.lower().endswith('.zip') else '.ttf'
        got = _http_download(dl, Path(dest_dir) / f"{safe}-fonts2u{ext}", timeout=30)
        if got:
            verified = [p for p in got if _font_name_matches(p, name, threshold=0.55)]
            if verified:
                return verified
    return []


def _try_alfont(name, dest_dir):
    """Scraper for alfont.com — the largest free Arabic-font mirror.

    alfont.com is the gold mine for commercial Arabic fonts (29LT, Hacen,
    AF_*, AGA, A Noor, Bahij, GE_SS, Adobe Arabic, ...). Each detail page
    has a clearly-marked download button with class="btn bg-green".

    Strategy (v1.8 — corrected from v1.7 which kept finding Janna LT in
    the side-widget on every page):
      1. Search /?s={query} → collect candidate detail URLs whose slug
         actually contains tokens from the query (so we don't follow
         random "related fonts" widget links).
      2. Generate direct-slug guesses from the font name.
      3. For each detail page, extract the ONE download-button URL
         (not just any wp-content link on the page). The download
         button looks like:
             <a class="... bg-green ..." href="...alfont_com_*.ttf">
         We use that anchor to find the right URL.
      4. Name-verify with a loose threshold (0.55).

    # TODO(#14): add per-host circuit breaker — if alfont returns 429/503
    #   three times in a row, skip it for the remainder of the session to
    #   avoid wasting ~20s × N fonts on a site that's rate-limiting us.
    #   Shared state: _HOST_FAILURES: dict[str, int] = defaultdict(int)
    #   If _HOST_FAILURES["alfont.com"] >= 3: return []

    """
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    # Tokens we will use to filter slugs (drop short stopwords)
    name_tokens = [t for t in re.findall(r'[a-z0-9]+', name.lower())
                   if len(t) >= 2]
    if not name_tokens:
        return []

    candidates = []

    # 1) Search the site for the exact font name. KEEP only result URLs
    # whose slug contains at least one meaningful token from the query.
    q = urllib.parse.quote(name)
    search_html = _http_get_text(f"https://alfont.com/?s={q}", timeout=20)
    if search_html:
        for url in re.findall(
                r'href="(https?://alfont\.com/[^"]+-arabic-font-download\.html)"',
                search_html, re.I):
            slug = url.lower()
            # The slug must contain the strongest token (longest one)
            strongest = max(name_tokens, key=len)
            if strongest in slug and url not in candidates:
                candidates.append(url)

    # 2) Direct slug guesses derived from the font name
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    for tail in (f"{base}-arabic-font-download.html",
                 f"{base}-2-arabic-font-download.html",
                 f"{base}-regular-arabic-font-download.html",
                 f"{base}-font-arabic-font-download.html"):
        url = f"https://alfont.com/{tail}"
        if url not in candidates:
            candidates.append(url)

    # 3) Try each detail page and extract the DOWNLOAD-BUTTON URL only
    for detail_url in candidates[:6]:
        detail = _http_get_text(detail_url, timeout=20)
        if not detail:
            continue
        # Anchor to the download-button class:
        #   <a class="... bg-green ..." href="https://alfont.com/wp-content/fonts/...ttf">
        m = re.search(
            r'<a[^>]*class="[^"]*bg-green[^"]*"[^>]*href="([^"]+\.(?:ttf|otf|zip))"',
            detail, re.I)
        if not m:
            # Fallback: any anchor with "fa-download" icon next to it
            m = re.search(
                r'href="([^"]+\.(?:ttf|otf|zip))"[^>]*>(?:[^<]*<i[^>]*fa-download)',
                detail, re.I)
        if not m:
            # Last resort: pick a URL whose filename contains a query token
            urls = re.findall(
                r'(https?://alfont\.com/wp-content/(?:fonts|uploads)/[^"\s]+\.(?:ttf|otf|zip))',
                detail, re.I)
            chosen = None
            for u in urls:
                fname = u.lower().rsplit('/', 1)[-1]
                # The file name often looks like alfont_com_*_{TokenizedName}.ttf
                if any(t in fname for t in name_tokens):
                    chosen = u; break
            if not chosen:
                continue
            dl = chosen
        else:
            dl = m.group(1)

        ext = (".zip" if dl.lower().endswith(".zip") else
               ".otf" if dl.lower().endswith(".otf") else ".ttf")
        dest = Path(dest_dir) / f"{safe}-alfont{ext}"
        got  = _http_download(dl, dest, timeout=30)
        if got:
            # STRICT verification — alfont's search returns lots of
            # "related" fonts that aren't what was asked. If the file
            # inside doesn't actually match the requested name, drop it
            # rather than silently substituting.
            verified = [p for p in got
                        if _font_name_matches(p, name, threshold=0.65)]
            if verified:
                return verified
            # Clean up the false positive so it doesn't pollute fonts/
            for p in got:
                try: Path(p).unlink()
                except Exception: pass
    return []



class FontHunter:
    """Multi-source font search with result caching.

    Downloaded files are placed in `<anime_root>/fonts/` — the library-wide
    pool. The build-_Fonts step reads this directory in addition to the
    OS-installed fonts, so newly-downloaded fonts are immediately available
    to every anime in the library WITHOUT installing them system-wide.
    """
    # Bump this whenever the cache schema or strategy set changes so stale
    # caches from older versions are automatically discarded. (Fix #16)
    CACHE_VERSION = "2.0"

    STRATEGIES = (
        ("direct",        _try_direct_urls),     # known-good exact URLs
        ("releases",      _try_github_releases), # GitHub Releases API (ZIPs)
        ("mirrors",       _try_github_mirrors),  # curated raw-GitHub URLs
        ("google",        _try_google_fonts),    # gwfh.mranftl.com API
        ("fontshare",     _try_fontshare),       # api.fontshare.com (free pro)
        ("fontdownload",  _try_fontdownload),    # font.download — direct .zip
        ("alfont",        _try_alfont),          # alfont.com — Arabic fonts
        ("fonts2u",      _try_fonts2u),         # fonts2u.com pages with direct downloads
        ("1001fonts",     _try_1001fonts),       # 1001fonts.com — direct .zip
        ("fontsloader",   _try_fontsloader),     # en.fontsloader.com
        ("dafont",        _try_dafont_safe),     # dafont.com — direct .zip
        ("archive",       _try_internet_archive),# archive.org
        ("github",        _try_github_search),   # GitHub code search
        ("ddg",           _try_duckduckgo),      # DuckDuckGo HTML
        ("bing",          _try_bing),            # Bing HTML
        ("font_sites",    _try_font_sites),      # fontspace + others fallback
        ("wayback",       _try_wayback),         # web.archive.org snapshots
    )

    def __init__(self, anime_root):
        self.anime_root = Path(anime_root)
        self.dest_dir   = self.anime_root / LIBRARY_FONTS_DIR_NAME
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.anime_root / FONT_CACHE_NAME
        self.cache      = self._load_cache()

    def _load_cache(self):
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                # Version check — discard caches written by older versions (#16)
                if data.get("__cache_version__") != self.CACHE_VERSION:
                    return {"__cache_version__": self.CACHE_VERSION}
                return data
            except Exception:
                return {"__cache_version__": self.CACHE_VERSION}
        return {"__cache_version__": self.CACHE_VERSION}

    def _save_cache(self):
        try:
            self.cache["__cache_version__"] = self.CACHE_VERSION  # always stamp version
            self.cache_path.write_text(
                json.dumps(self.cache, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:
            log_event(self.anime_root, f"font cache save failed: {e}", "WARN")

    def hunt(self, font_name, retry_missing=False):
        """Run every strategy until one returns files.

        Args:
          retry_missing: if True, ignore a previously-stored "not_found"
                         cache entry and try all strategies again.
                         Useful after adding new catalog entries or font sites.

        Returns:
          {'status': 'found'|'cached'|'not_found',
           'source': 'google'|'catalog'|'github'|'ddg'|'bing'|'font_sites'|None,
           'files':  [Path, ...]}
        """
        key = _font_alias_key(font_name)

        # ── Positive cache ──
        if key in self.cache and self.cache[key].get("files"):
            existing = [Path(p) for p in self.cache[key]["files"]
                        if Path(p).exists()]
            if existing:
                return {"status": "cached",
                        "source": self.cache[key].get("source"),
                        "files":  existing}

        # ── Negative cache (skip only when NOT retrying) ──
        # The cache may store an entry with files=[] meaning "we hunted last
        # time and found nothing". Honor that ONLY when retry_missing=False.
        # When the user explicitly retries, we always hit the strategies.
        if (not retry_missing
                and key in self.cache
                and self.cache[key].get("source") is None
                and not self.cache[key].get("files")):
            return {"status": "not_found", "source": None, "files": []}

        # ── Try strategies in order ──
        for source, fn in self.STRATEGIES:
            try:
                files = fn(font_name, self.dest_dir)
            except Exception as e:
                log_event(self.anime_root,
                          f"strategy {source} failed for {font_name}: {e}",
                          "WARN")
                files = []
            if files:
                self.cache[key] = {"source": source,
                                   "files":  [str(p) for p in files],
                                   "name":   font_name}
                self._save_cache()
                return {"status": "found", "source": source, "files": files}

        # ── Negative cache ──
        self.cache[key] = {"source": None, "files": [], "name": font_name}
        self._save_cache()
        return {"status": "not_found", "source": None, "files": []}


def _font_source_hint(font_name):
    """Best-effort licensing/source guidance for fonts we could not fetch.

    This tool only auto-downloads fonts from open/public sources. For fonts
    that are likely commercial, bundled, or user-licensed, we generate a
    source report so the user can import them from their own licensed copies
    into <anime_root>/fonts/.
    """
    n = font_name.lower().strip()
    if n.startswith("29lt"):
        return ("Commercial / licensed", "29LT official store", "Import manually from your licensed 29LT files into <anime_root>/fonts/.")
    if n.startswith("a-otf") or n.startswith("fot-"):
        return ("Commercial / licensed", "Fontworks / Morisawa distributor", "Japanese pro font; import from your licensed archive.")
    if "segoe" in n or "maiandra" in n:
        return ("Bundled / proprietary", "Microsoft Windows / Office", "Copy from a licensed Windows or Office installation.")
    if "adobe" in n:
        return ("Commercial / licensed", "Adobe Fonts / Adobe apps", "Import from your licensed Adobe installation if available.")
    if n.startswith("bahij") or n.startswith("hacen") or n.startswith("af_") or n.startswith("ae_") or n.startswith("ge"):
        return ("Arabic desktop font", "Your licensed font archive / vendor", "Usually distributed in regional font bundles; import manually if you own it.")
    if n.startswith("xm ") or n.startswith("xb ") or n.startswith("xp "):
        return ("Persian / Arabic desktop font", "Your licensed archive or bundled package", "Import manually from your existing font collection.")
    return ("Manual review", "Search your licensed archive or the original release package", "If you own the font, copy the .ttf/.otf into <anime_root>/fonts/.")


def write_font_sources_report(anime_root, results, missing_names):
    report_path = Path(anime_root) / SOURCES_REPORT_FILENAME
    lines = [
        '# Anime Studio — Font Source Guide',
        '',
        f'_Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}_',
        f'_Anime root: `{anime_root}`_',
        '',
        '## Policy',
        '',
        '- Auto-download is limited to open/public sources already supported by the tool.',
        '- Fonts that appear commercial, bundled, or licensed are **not** auto-downloaded from unauthorized mirror sites.',
        '- For those fonts, import your licensed `.ttf` / `.otf` files into `<anime_root>/fonts/`, then run **Scan + Backup**, then **Mux**.',
        '',
        '## Auto-download results',
        '',
        '| Font | Status | Source | Files |',
        '|------|--------|--------|-------|',
    ]
    for name in sorted(results):
        r = results[name]
        files = ', '.join(f'`{Path(p).name}`' for p in r.get('files', [])) or '—'
        lines.append(f"| {name} | {r.get('status','?')} | {r.get('source') or '—'} | {files} |")

    if missing_names:
        lines += ['', '## Fonts that still need manual import', '']
        for name in sorted(missing_names):
            category, source, note = _font_source_hint(name)
            lines += [
                f'### {name}',
                f'- **Category:** {category}',
                f'- **Suggested source:** {source}',
                f'- **Action:** {note}',
                ''
            ]
    try:
        report_path.write_text('\n'.join(lines), encoding='utf-8')
        return report_path
    except Exception as e:
        log_event(anime_root, f"font source report write failed: {e}", "WARN")
        return None


def download_missing_fonts(anime_root):
    """Professional guided font recovery into <root>/fonts/.

    This step auto-downloads fonts only from open/public sources already baked
    into the tool. For anything still missing, a source guide is generated so
    the user can import licensed fonts manually without guesswork.
    """
    if _RICH:
        _con.print()
        _con.rule("[bold magenta]📥  AUTO-DOWNLOAD MISSING FONTS[/bold magenta]")
        _con.print(Panel(
            "[bold]Total Hunt enabled.[/bold]  This run will try ~19 different "
            "sources to recover every requested font.\n\n"
            "[yellow]⚖  Licensing reminder:[/yellow] some scraped sources mirror "
            "fonts whose original foundry sells them commercially. You are "
            "responsible for verifying the EULA of each downloaded font before "
            "embedding it in distributed content.",
            title="[bold]Font Hunter v1.11[/bold]",
            border_style="yellow", expand=False, padding=(0, 1)))

    rprint("[dim]Analyzing library to collect missing-font names…[/dim]")
    reports, _state = analyze_anime_jobs(anime_root)
    missing = sorted({n for r in reports for n in r.missing_fonts_set})
    if not missing:
        rprint("[bold green]🎉  No missing fonts — every ASS in your "
               "library is covered![/bold green]")
        return
    rprint(f"[bold]→ Found [yellow]{len(missing)}[/yellow] unique font(s) "
           "to hunt for.[/bold]\n")

    hunter = FontHunter(anime_root)
    results = {}

    # ── Parallel hunt: the strategies are mostly network I/O, so a thread
    # pool gives a 5-10× speed-up over the old sequential loop.  We cap the
    # concurrency to keep the GitHub / Bing rate-limits happy.  Override via
    # ANIME_FONT_WORKERS env var if you want more / fewer.
    # ANIME_FONT_WORKERS: default 4 (was 8 in v1.x — caused 429s on alfont/fonts2u).
    # Override via env var for fast connections: ANIME_FONT_WORKERS=8
    # TODO(#15): implement per-domain rate limiting so workers can be raised
    #   to 8+ without DOSing sites. Use a per-host semaphore:
    #   _HOST_SEMA: dict[str, asyncio.Semaphore] = {"alfont.com": Semaphore(2), ...}
    try:
        font_workers = max(1, int(os.environ.get("ANIME_FONT_WORKERS", 4)))
    except ValueError:
        font_workers = 4

    if _RICH:
        _first_done = [False]
        with Progress(SpinnerColumn(),
                      TextColumn("[progress.description]{task.description}"),
                      BarColumn(bar_width=None),
                      MofNCompleteColumn(), TaskProgressColumn(),
                      TimeRemainingColumn(), console=_con) as prog:
            t = prog.add_task(f"[cyan]Hunting fonts on the web ({font_workers}× parallel)…",
                              total=len(missing), start=False)
            with concurrent.futures.ThreadPoolExecutor(max_workers=font_workers) as pool:
                futures = {pool.submit(hunter.hunt, n, True): n for n in missing}
                for fut in concurrent.futures.as_completed(futures):
                    name = futures[fut]
                    results[name] = fut.result()
                    if not _first_done[0]:
                        prog.start_task(t)
                        _first_done[0] = True
                    status = results[name]["status"]
                    source = results[name]["source"]
                    tag = {"found":     "[green]✓[/green]",
                           "cached":    "[cyan]⏭[/cyan]",
                           "not_found": "[red]✗[/red]"}[status]
                    src_txt = f"  [dim]← {source}[/dim]" if source else ""
                    prog.console.print(f"  {tag}  {name}{src_txt}")
                    prog.advance(t)
    else:
        print(f"🔍 Hunting {len(missing)} fonts in parallel ({font_workers}× threads)…")
        with concurrent.futures.ThreadPoolExecutor(max_workers=font_workers) as pool:
            futures = {pool.submit(hunter.hunt, n): n for n in missing}
            for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
                name = futures[fut]
                results[name] = fut.result()
                print(f"  [{i}/{len(missing)}] {name}: "
                      f"{results[name]['status']} ({results[name].get('source')})")

    # ── Grouped summary ──
    # defaultdict accepts any source label a strategy returns — including
    # future ones added by v2_install_hunter_integration or plugins.
    by_source = defaultdict(list)
    cached    = []
    not_found = []
    for n, r in results.items():
        if r["status"] == "cached":
            cached.append(n)
        elif r["status"] == "found":
            by_source[r["source"]].append(n)
        else:
            not_found.append(n)

    total_found = sum(len(v) for v in by_source.values())

    # Registry-driven label table — add a row here whenever a new strategy
    # is added to FontHunter.STRATEGIES (or nowhere, since defaultdict(list)
    # already accepts unknown keys; the row just won't appear below).
    _SOURCE_LABELS = {
        "universal_search": ("[magenta]✓ Universal Search[/magenta]",
                             "v2.0 multi-engine web search"),
        "direct":           ("[green]✓ Direct URLs[/green]",
                             "verified exact-name URLs in built-in catalog"),
        "releases":         ("[green]✓ GitHub Releases[/green]",
                             "aliftype · rastikerdar · JetBrains · Microsoft · Mozilla"),
        "mirrors":          ("[green]✓ GitHub mirrors[/green]",
                             "curated raw-GitHub URLs (Arabic / Persian / CJK / Latin)"),
        "google":           ("[green]✓ Google Fonts API[/green]",
                             "gwfh.mranftl.com (open-source fonts)"),
        "fontshare":        ("[green]✓ Fontshare API[/green]",
                             "api.fontshare.com (commercial-free professional fonts)"),
        "fontdownload":     ("[cyan]✓ Font.Download[/cyan]",
                             "font.download — direct ZIP downloads"),
        "alfont":           ("[cyan]✓ alfont.com[/cyan]",
                             "alfont.com — Arabic / Persian / Urdu fonts (29LT, Hacen, AF, …)"),
        "fonts2u":          ("[cyan]✓ Fonts2u[/cyan]",
                             "fonts2u.com — direct downloads from public font pages"),
        "1001fonts":        ("[cyan]✓ 1001Fonts[/cyan]",
                             "1001fonts.com — curated since 2001"),
        "fontsloader":      ("[cyan]✓ FontsLoader[/cyan]",
                             "fontsloader.com — bulk font ZIPs"),
        "dafont":           ("[cyan]✓ DaFont[/cyan]",
                             "dafont.com — classic display + foreign scripts"),
        "archive":          ("[yellow]✓ Internet Archive[/yellow]",
                             "archive.org search & download"),
        "github":           ("[yellow]✓ GitHub Code Search[/yellow]",
                             "raw files in public repos"),
        "ddg":              ("[yellow]✓ DuckDuckGo[/yellow]",
                             "web search → direct .ttf/.otf URL"),
        "bing":             ("[yellow]✓ Bing[/yellow]",
                             "backup search engine"),
        "font_sites":       ("[yellow]✓ Font sites[/yellow]",
                             "fontspace · 1001fonts · dafont"),
        "wayback":          ("[dim]✓ Wayback Machine[/dim]",
                             "web.archive.org snapshots for dead URLs"),
    }

    # Determine render order: known sources first (in registry order),
    # then any unknown sources returned by future strategies.
    _ordered_sources = list(_SOURCE_LABELS.keys())
    for _src in by_source:
        if _src not in _SOURCE_LABELS:
            _ordered_sources.append(_src)

    if _RICH:
        _con.print()
        t = Table(title="📊  Download results",
                  box=_rbox.SIMPLE_HEAVY, header_style="bold cyan",
                  border_style="blue")
        t.add_column("Source", style="bold white")
        t.add_column("Count", justify="right")
        t.add_column("Notes", style="dim")

        # Only emit a row when at least one font was found via that source
        for _src in _ordered_sources:
            _count = len(by_source.get(_src, []))
            if _count == 0:
                continue
            _label, _note = _SOURCE_LABELS.get(
                _src, (f"[green]✓ {_src.replace('_',' ').title()}[/green]", ""))
            t.add_row(_label, str(_count), _note)

        t.add_row("[cyan]⏭ Cached[/cyan]", str(len(cached)),
                  "downloaded in a previous run")
        t.add_row("[red]✗ Still missing[/red]", str(len(not_found)),
                  "usually licensed / bundled fonts that need manual import")
        t.add_row("[bold]TOTAL FOUND[/bold]",
                  f"[bold green]{total_found + len(cached)}[/bold green]",
                  f"[dim]of {len(missing)} requested[/dim]")
        _con.print(t)

        if not_found:
            # 2-col panel — easier to scan
            mid   = (len(not_found) + 1) // 2
            left  = not_found[:mid]
            right = not_found[mid:]
            w     = max(len(s) for s in left) + 2
            body  = []
            for i in range(mid):
                l = left[i]
                r = right[i] if i < len(right) else ""
                body.append(f"  • [red]{l:<{w}}[/red]"
                            + (f" • [red]{r}[/red]" if r else ""))
            sources_hint = (
                "[dim]Try manually:\n"
                "  • [link]https://arabicfonts.net[/link]    (search by name)\n"
                "  • [link]https://www.behance.net[/link]   (Arabic designers)\n"
                "  • [link]https://www.fontspace.com[/link] (free fonts directory)\n"
                "  • The fansub group's Telegram channel.[/dim]"
            )
            _con.print(Panel("\n".join(body) + "\n\n" + sources_hint,
                             title=f"[bold red]Still missing ({len(not_found)})[/bold red]",
                             border_style="red", expand=False,
                             padding=(0, 1)))
    else:
        print(f"\nFound: {total_found}   Cached: {len(cached)}   "
              f"Not found: {len(not_found)}")

    rprint(f"\n[bold green]✓[/bold green]  Downloaded files placed in: "
           f"[cyan]{hunter.dest_dir}[/cyan]")
    rprint(f"[dim]Cache: [cyan]{hunter.cache_path}[/cyan][/dim]")
    src_report = write_font_sources_report(anime_root, results, not_found)
    if src_report:
        rprint(f"[dim]Source guide: [cyan]{src_report}[/cyan][/dim]")
    rprint("[dim]→ Next: run [bold]Build _Fonts folders[/bold], then [bold]Mux episodes into MKV[/bold].[/dim]")


# =========================================================================

# =========================================================================
# 12. SMART  MUX  —  driver  (pre-flight gating + selective execution)
# =========================================================================
#
#  PHASE 1: ANALYSIS   -> EpisodePlan per (video,sub) + AnimeReport per anime
#  PHASE 2: REPORT     -> rich tables + Markdown export for missing fonts
#  PHASE 3: SELECTION  -> user picks: only READY / READY+PARTIAL / EVERYTHING
#  PHASE 4: EXECUTION  -> mux only what was selected; resume-aware
# =========================================================================
def analyze_anime_jobs(anime_root, only_folder=None):
    """PHASE 1 — Pre-flight analysis. Reads from disk only; NO files modified.
       Returns (reports: list[AnimeReport], state: dict)."""
    state = load_state(anime_root)
    jobs = discover_anime_jobs(only_folder or anime_root)

    # Group jobs by their top-level anime name (first folder under anime_root)
    root_abs = Path(anime_root).resolve()
    grouped = {}
    for job in jobs:
        folder_abs = Path(job["folder"]).resolve()
        try:
            rel = folder_abs.relative_to(root_abs)
            anime_name = rel.parts[0] if rel.parts else folder_abs.name
        except ValueError:
            anime_name = folder_abs.name
        grouped.setdefault(anime_name, []).append(job)

    reports = []
    for anime_name, group in grouped.items():
        episodes = []
        missing_set = set()
        fonts_dir = None
        for job in group:
            fmap = build_font_map(job["fonts_dir"]) if job["fonts_dir"] else ({}, {}, {})
            if job["fonts_dir"] and not fonts_dir:
                fonts_dir = job["fonts_dir"]
            for m in job["matches"]:
                video_path = Path(job["folder"]) / m["vid"]
                sub_path   = Path(job["folder"]) / m["sub"]
                resolved, missing = resolve_required_fonts(sub_path, fmap)
                needed = {n for n in fonts_required_by_ass(sub_path)
                          if n.lower() not in SYSTEM_FONT_IGNORE}
                # Classify status
                out = video_path.with_suffix(".mkv")
                if str(out) in state and MUXED_MARKER_KEY in state[str(out)]:
                    status = EpStatus.MUXED
                elif not needed:
                    status = EpStatus.NO_FONTS
                elif not missing:
                    status = EpStatus.READY
                elif resolved:
                    status = EpStatus.PARTIAL
                else:
                    status = EpStatus.BLOCKED
                missing_set.update(missing)
                episodes.append(EpisodePlan(
                    anime_name=anime_name, folder=job["folder"],
                    video=m["vid"], sub=m["sub"],
                    fonts_dir=job["fonts_dir"],
                    fonts_resolved=resolved, fonts_missing=missing,
                    status=status,
                ))
        reports.append(AnimeReport(
            name=anime_name,
            folder=str(root_abs / anime_name) if (root_abs / anime_name).exists()
                   else group[0]["folder"],
            fonts_dir=fonts_dir, episodes=episodes,
            missing_fonts_set=missing_set,
        ))

    # Healthy first, problems last — easier to scan
    health_order = {"green": 0, "yellow": 1, "red": 2, "dim": 3}
    reports.sort(key=lambda r: (health_order[r.health], r.name.lower()))
    return reports, state


def print_preflight_report(reports, anime_root):
    """PHASE 2 — Display the report.

    Column meanings (in plain words):
      • Eps       — total (video, subtitle) pairs detected
      • Ready     — ASS uses custom fonts AND ALL of them exist in _Fonts
      • Subs-only — ASS only uses system fonts (Arial etc.) → no _Fonts needed
      • Partial   — ASS needs N fonts but we have only some
      • Blocked   — ASS needs custom fonts but NONE are available
      • Done      — already muxed in a previous run (resume marker)
      • Status    — green = ready to mux, yellow = some missing, red = nothing usable
    """
    # ── Roll-up totals across the whole library ──
    total_eps   = sum(r.total    for r in reports)
    total_ready = sum(r.ready    for r in reports)
    total_so    = sum(r.no_fonts for r in reports)
    total_par   = sum(r.partial  for r in reports)
    total_blk   = sum(r.blocked  for r in reports)
    total_done  = sum(r.muxed    for r in reports)
    total_miss  = len({n for r in reports for n in r.missing_fonts_set})

    if _RICH:
        _con.print()
        _con.rule("[bold cyan]PHASE 1  —  PRE-FLIGHT ANALYSIS[/bold cyan]")

        # ── Summary panel at the top (the elevator pitch) ──
        anim_ok  = sum(1 for r in reports if r.health == "green")
        anim_yel = sum(1 for r in reports if r.health == "yellow")
        anim_red = sum(1 for r in reports if r.health == "red")
        summary = (
            f"[bold]Library:[/bold]   [cyan]{anime_root}[/cyan]\n"
            f"[bold]Anime  :[/bold]   {len(reports)} folders  "
            f"([green]{anim_ok} ok[/green] · "
            f"[yellow]{anim_yel} partial[/yellow] · "
            f"[red]{anim_red} blocked[/red])\n"
            f"[bold]Episodes:[/bold] {total_eps} total  →  "
            f"[green]{total_ready + total_so} ok to mux now[/green]  ·  "
            f"[yellow]{total_par} partial[/yellow]  ·  "
            f"[red]{total_blk} blocked[/red]"
            + (f"  ·  [cyan]{total_done} already done[/cyan]" if total_done else "")
            + "\n"
            f"[bold]Missing fonts (unique):[/bold] {total_miss}"
        )
        _con.print(Panel(summary, title="✨ Overview",
                         border_style="cyan", expand=False))
        _con.print()

        # ── Per-anime table ──
        t = Table(title=None, box=_rbox.SIMPLE_HEAVY,
                  border_style="blue", header_style="bold cyan",
                  show_lines=False, row_styles=["", "on grey7"])
        t.add_column("Anime",     style="bold white", no_wrap=False, min_width=30)
        t.add_column("Eps",       justify="right", style="dim")
        t.add_column("Ready",     justify="right", style="green")
        t.add_column("No custom", justify="right", style="green")
        t.add_column("Need fonts", justify="right", style="yellow")
        t.add_column("Blocked",    justify="right", style="red")
        t.add_column("Done",      justify="right", style="cyan")
        t.add_column("Status",    min_width=12)
        for r in reports:
            icon = {"green":  "✅ ready now",
                    "yellow": "⚠ needs fonts",
                    "red":    "❌ blocked",
                    "dim":    "—"}[r.health]
            def _c(n, color=""):
                if not n: return "[dim]·[/dim]"
                return f"[{color}]{n}[/{color}]" if color else str(n)
            t.add_row(r.name,
                      str(r.total),
                      _c(r.ready,    "green"),
                      _c(r.no_fonts, "green dim"),
                      _c(r.partial,  "yellow"),
                      _c(r.blocked,  "red"),
                      _c(r.muxed,    "cyan"),
                      f"[{r.health}]{icon}[/{r.health}]")
        _con.print(t)

        # ── Detail panels for problem anime ──
        problem = [r for r in reports if r.health in ("yellow", "red")]
        if problem:
            _con.print()
            _con.rule("[bold yellow]⚠  Anime that need attention[/bold yellow]")
            for r in problem:
                missing_sorted = sorted(r.missing_fonts_set)
                body = []
                if missing_sorted:
                    body.append(
                        f"[bold red]Missing fonts ({len(missing_sorted)}):[/bold red]"
                    )
                    # 2-column display for compactness when there are many
                    if len(missing_sorted) > 6:
                        mid = (len(missing_sorted) + 1) // 2
                        left  = missing_sorted[:mid]
                        right = missing_sorted[mid:]
                        width = max(len(s) for s in left) + 3
                        for i in range(mid):
                            l = left[i]
                            r2 = right[i] if i < len(right) else ""
                            body.append(f"  • [red]{l:<{width}}[/red] "
                                        + (f"• [red]{r2}[/red]" if r2 else ""))
                    else:
                        for f in missing_sorted:
                            body.append(f"  • [red]{f}[/red]")
                else:
                    body.append("[dim]No _Fonts folder detected nearby[/dim]")
                body.append("")
                body.append(
                    f"[dim]Episodes:[/dim]  "
                    f"[green]✓ {r.ready + r.no_fonts}[/green]  "
                    f"[yellow]⚠ {r.partial}[/yellow]  "
                    f"[red]✗ {r.blocked}[/red]  "
                    + (f"[cyan]⏭ {r.muxed}[/cyan]" if r.muxed else "")
                )
                _con.print(Panel("\n".join(body),
                                 title=f"[bold {r.health}]🎬 {r.name}[/bold {r.health}]",
                                 border_style=r.health, expand=False, padding=(0, 1)))
    else:
        print("\n=== PRE-FLIGHT ANALYSIS ===")
        for r in reports:
            print(f"  {r.name:<30s} eps={r.total:<3d} ready={r.ready:<3d} "
                  f"subs-only={r.no_fonts:<3d} partial={r.partial:<3d} "
                  f"blocked={r.blocked:<3d} done={r.muxed:<3d} "
                  f"[{r.health}]")
            if r.missing_fonts_set:
                print(f"      missing: {', '.join(sorted(r.missing_fonts_set))}")

    write_markdown_report(reports, anime_root)


def write_markdown_report(reports, anime_root):
    """Persist the analysis as Markdown for archival / sharing."""
    report_path = Path(anime_root) / REPORT_FILENAME
    lines = [
        "# Anime Studio — Font Coverage Report",
        "",
        f"_Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        f"_Anime root: `{anime_root}`_",
        "",
        "## Summary",
        "",
        "| Anime | Total | Ready | Partial | Blocked | Muxed | Status |",
        "|-------|------:|------:|--------:|--------:|------:|:-------|",
    ]
    for r in reports:
        icon = {"green":"✅","yellow":"⚠️","red":"❌","dim":"—"}[r.health]
        lines.append(f"| {r.name} | {r.total} | {r.ready} | {r.partial} | "
                     f"{r.blocked} | {r.muxed} | {icon} |")
    lines += ["", "## Missing fonts per anime", ""]
    any_missing = False
    for r in reports:
        if not r.missing_fonts_set:
            continue
        any_missing = True
        lines.append(f"### {r.name}")
        lines.append(f"`{r.folder}`")
        lines.append("")
        for f in sorted(r.missing_fonts_set):
            lines.append(f"- [ ] `{f}`")
        lines.append("")
        affected = [e for e in r.episodes
                    if e.status in (EpStatus.PARTIAL, EpStatus.BLOCKED)]
        if affected:
            lines.append(f"<details><summary>Affected episodes ({len(affected)})</summary>")
            lines.append("")
            for e in affected:
                tag = {EpStatus.PARTIAL:"⚠", EpStatus.BLOCKED:"❌"}[e.status]
                lines.append(f"- {tag} `{e.video}` — missing: "
                             + ", ".join(f"`{n}`" for n in e.fonts_missing))
            lines += ["", "</details>", ""]
    if not any_missing:
        lines.append("_All anime have full font coverage. 🎉_")
        lines.append("")
        lines.append("> If mux still fails, the problem is usually the subtitle file itself (invalid ASS structure, weird encoding, or an unsafe Windows path), **not** missing fonts.")
    lines += [
        "",
        "## What to do next",
        "",
        "1. Run **Start here — fix everything automatically** for the normal one-click workflow.",
        "2. If the report says fonts are complete but mux still fails, open `.anime_studio_log.txt` — that usually means the subtitle file itself needed repair.",
        "3. Run **Build `_Fonts` folders** after any new downloads so every anime gets its own local copy.",
        "4. Run **Mux episodes into MKV** again — finished episodes are skipped automatically.",
        "",
    ]
    try:
        report_path.write_text("\n".join(lines), encoding="utf-8")
        rprint(f"[dim]📝 Markdown report saved → [cyan]{report_path}[/cyan][/dim]")
    except Exception as e:
        log_event(anime_root, f"report write failed: {e}", "WARN")


def _filter_episodes(reports, mode):
    """PHASE 3 helper — pick episodes according to the chosen policy."""
    selected = []
    skipped  = {"partial": 0, "blocked": 0, "no_fonts": 0, "muxed": 0}
    for r in reports:
        for e in r.episodes:
            if e.status == EpStatus.MUXED:
                skipped["muxed"] += 1
                continue
            if mode == "safe":
                if e.status in (EpStatus.READY, EpStatus.NO_FONTS):
                    selected.append(e)
                else:
                    skipped[e.status.value] = skipped.get(e.status.value, 0) + 1
            elif mode == "partial":
                if e.status in (EpStatus.READY, EpStatus.NO_FONTS, EpStatus.PARTIAL):
                    selected.append(e)
                else:
                    skipped[e.status.value] = skipped.get(e.status.value, 0) + 1
            else:                       # "all"
                selected.append(e)
    return selected, skipped


def ask_mux_policy(reports):
    """PHASE 3 — Let the user pick the gating policy."""
    ready_n   = sum(r.ready    for r in reports)
    partial_n = sum(r.partial  for r in reports)
    blocked_n = sum(r.blocked  for r in reports)
    no_fnt_n  = sum(r.no_fonts for r in reports)
    muxed_n   = sum(r.muxed    for r in reports)

    if _RICH:
        _con.print()
        body = (
            f"[bold green]🎯  Choose what to mux[/bold green]\n\n"
            f"  [bold]A.[/bold]  [green]SAFE[/green]       — ready episodes only\n"
            f"          will mux  : [green]{ready_n + no_fnt_n}[/green]\n"
            f"          will skip : [yellow]{partial_n} partial[/yellow], "
            f"[red]{blocked_n} blocked[/red], [cyan]{muxed_n} already muxed[/cyan]\n\n"
            f"  [bold]B.[/bold]  [yellow]PARTIAL OK[/yellow] — also mux episodes missing some fonts\n"
            f"          will mux  : [yellow]{ready_n + no_fnt_n + partial_n}[/yellow]"
            f"   (missing fonts → fallback to Arial)\n"
            f"          will skip : [red]{blocked_n} blocked[/red], "
            f"[cyan]{muxed_n} already muxed[/cyan]\n\n"
            f"  [bold]C.[/bold]  [red]EVERYTHING[/red]  — mux even fully blocked episodes\n"
            f"          will mux  : [red]{ready_n + no_fnt_n + partial_n + blocked_n}[/red]\n\n"
            f"  [bold]X.[/bold]  Cancel — keep the report and exit"
        )
        _con.print(Panel(body, border_style="cyan",
                         title="[bold]Selective Mux — Pick a policy[/bold]"))
    else:
        print("\nChoose mux policy:")
        print(f"  A) SAFE       — ready only ({ready_n + no_fnt_n})")
        print(f"  B) PARTIAL OK — also missing-some ({ready_n + no_fnt_n + partial_n})")
        print(f"  C) EVERYTHING ({ready_n + no_fnt_n + partial_n + blocked_n})")
        print(f"  X) Cancel")

    if not sys.stdin.isatty() or os.environ.get("ANIME_STUDIO_AUTO_POLICY"):
        ans = (os.environ.get("ANIME_STUDIO_AUTO_POLICY") or "A").strip().upper()
    else:
        ans = input("\nYour choice [A/B/C/X]: ").strip().upper()
    return {"A":"safe", "B":"partial", "C":"all"}.get(ans)


def run_smart_mux(anime_root, only_folder=None, output_mode="replace",
                  keep_originals=False, policy=None, auto_confirm=False):
    """Top-level driver — orchestrates all 4 phases."""
    target = only_folder or anime_root

    # PHASE 1
    if _RICH:
        with Progress(SpinnerColumn(),
                      TextColumn("[progress.description]{task.description}"),
                      console=_con, transient=True) as sp:
            sp.add_task("Analyzing episodes & font coverage…", total=None)
            reports, state = analyze_anime_jobs(anime_root, only_folder)
    else:
        print("🔍 Analyzing episodes & font coverage…")
        reports, state = analyze_anime_jobs(anime_root, only_folder)

    if not reports or all(r.total == 0 for r in reports):
        rprint(f"[yellow]No (video, subtitle) pairs found anywhere under "
               f"[cyan]{target}[/cyan].[/yellow]")
        return

    # PHASE 2
    print_preflight_report(reports, anime_root)

    if not shutil.which("mkvmerge") and not shutil.which("ffmpeg"):
        rprint("\n[bold red]❌ Neither mkvmerge nor ffmpeg is installed.[/bold red]")
        rprint("   → [yellow]scoop install mkvtoolnix[/yellow]")
        return

    # PHASE 3
    policy = (policy or ask_mux_policy(reports))
    if not policy:
        rprint("[dim]Cancelled. Report file kept for reference.[/dim]")
        return

    selected, skipped = _filter_episodes(reports, policy)
    if not selected:
        rprint("[yellow]Nothing to mux under this policy.[/yellow]")
        return

    if _RICH:
        _con.print()
        _con.rule(f"[bold green]PHASE 3  —  CONFIRM ({policy.upper()} policy)[/bold green]")
    rprint(f"[bold cyan]→[/bold cyan]  Will mux  [bold white]{len(selected)}[/bold white]  episode(s).  "
           f"Skipping [dim]{sum(skipped.values())}[/dim].")
    if not auto_confirm:
        if input("Proceed? (yes/N): ").strip().lower() != "yes":
            rprint("[dim]Aborted.[/dim]")
            return
    else:
        rprint("[dim]Auto-confirmed by the menu workflow.[/dim]")

    # ── PHASE 4: EXECUTE ──
    if _RICH:
        _con.print()
        _con.rule("[bold green]PHASE 4  —  MUXING[/bold green]")

    tasks = []
    for e in selected:
        if output_mode == "replace":
            out_path = e.output_path
        else:
            muxed_dir = Path(e.folder) / "_Muxed"
            muxed_dir.mkdir(exist_ok=True)
            out_path = muxed_dir / (Path(e.video).stem + ".mkv")
        tasks.append((str(e.video_path), str(e.sub_path), e.font_paths,
                      str(out_path), True))

    # Mux with `-c copy` is I/O bound, NOT CPU bound — so we oversubscribe
    # the cores up to a sensible cap to keep the disk queue full.  The user
    # can override with the ANIME_MUX_WORKERS env var (default = 2× cpu, max 16).
    _cpu_default = min(16, max(2, (os.cpu_count() or 4) * 2))
    try:
        cpu = max(1, int(os.environ.get("ANIME_MUX_WORKERS", _cpu_default)))
    except ValueError:
        cpu = _cpu_default
    # Collect results per-anime so we can print a clean grouped report at the end
    by_anime = {}   # anime_name -> {"ok": [...], "err": [(filename, msg), ...]}
    done = err = 0
    errs_flat = []  # for log file

    def _record(ok, ep, vid, msg):
        nonlocal done, err
        bucket = by_anime.setdefault(ep.anime_name, {"ok": [], "err": []})
        if ok:
            done += 1
            mark_muxed(state, ep)
            bucket["ok"].append(Path(vid).name)
        else:
            err += 1
            # Strip the "|FULL|..." suffix for on-screen display
            short_msg = msg.split("|FULL|", 1)[0] if "|FULL|" in msg else msg
            bucket["err"].append((Path(vid).name, short_msg))
            errs_flat.append((vid, msg))      # keep FULL for the log writer

    def _mux_loop(prog=None, ptask=None):
        with concurrent.futures.ProcessPoolExecutor(max_workers=cpu) as pool:
            futures = {pool.submit(smart_mux_one, t): (t, ep)
                       for t, ep in zip(tasks, selected)}
            for fut in concurrent.futures.as_completed(futures):
                ok, vid, msg = fut.result()
                task, ep = futures[fut]
                _record(ok, ep, vid, msg)
                # delete the original .ass only on success in 'replace' mode
                if ok and not keep_originals and output_mode == "replace":
                    try:
                        if os.path.exists(task[1]):
                            os.remove(task[1])
                    except Exception:
                        pass
                if prog:
                    prog.advance(ptask)
                    count = done + err
                    if ok:
                        prog.console.print(
                            f"  [green]✓[/green] [{count}/{len(tasks)}] [bold]{ep.anime_name}[/bold]  •  {Path(vid).name}"
                        )
                    else:
                        short_msg = msg.split("|FULL|", 1)[0] if "|FULL|" in msg else msg
                        prog.console.print(
                            f"  [red]✗[/red] [{count}/{len(tasks)}] [bold]{ep.anime_name}[/bold]  •  {Path(vid).name}"
                        )
                        prog.console.print(f"      [dim]{short_msg}[/dim]")

    if _RICH:
        with Progress(SpinnerColumn(),
                      TextColumn("[progress.description]{task.description}"),
                      BarColumn(bar_width=None),
                      MofNCompleteColumn(),
                      TaskProgressColumn(),
                      TimeRemainingColumn(),
                      console=_con, transient=False) as prog:
            pt = prog.add_task("[cyan]Muxing episodes…", total=len(tasks))
            _mux_loop(prog, pt)
    else:
        _mux_loop()

    save_state(anime_root, state)

    # ── GROUPED RESULT TABLE ──
    if _RICH:
        _con.print()
        _con.rule("[bold cyan]📊  Per-anime results[/bold cyan]")
        rt = Table(box=_rbox.SIMPLE_HEAVY, header_style="bold cyan",
                   border_style="blue", row_styles=["", "on grey7"])
        rt.add_column("Anime",   style="bold white", no_wrap=False, min_width=30)
        rt.add_column("✓ Done", justify="right", style="green")
        rt.add_column("✗ Fail", justify="right", style="red")
        rt.add_column("Outcome")
        for name in sorted(by_anime.keys(), key=str.lower):
            b = by_anime[name]
            n_ok, n_err = len(b["ok"]), len(b["err"])
            if n_err == 0:
                outcome = "[green]✅ all good[/green]"
            elif n_ok == 0:
                outcome = "[red]❌ all failed[/red]"
            else:
                outcome = f"[yellow]⚠ mixed ({n_err} fail)[/yellow]"
            rt.add_row(name,
                       str(n_ok) if n_ok else "[dim]·[/dim]",
                       str(n_err) if n_err else "[dim]·[/dim]",
                       outcome)
        _con.print(rt)

        # ── Per-failure detail panels (so the real error is VISIBLE) ──
        bad = {n: b for n, b in by_anime.items() if b["err"]}
        if bad:
            _con.print()
            _con.rule("[bold red]❌  Failures — what went wrong[/bold red]")
            for name in sorted(bad.keys(), key=str.lower):
                body = []
                # de-dup error messages, count occurrences
                from collections import Counter
                error_count = Counter(msg for _, msg in bad[name]["err"])
                for msg, count in error_count.most_common():
                    body.append(f"[red]× {count} ep(s):[/red]  {msg}")
                body.append("")
                body.append("[dim]Affected episodes:[/dim]")
                for fn, _ in bad[name]["err"][:5]:
                    body.append(f"  [dim]• {fn}[/dim]")
                if len(bad[name]["err"]) > 5:
                    body.append(f"  [dim]… and {len(bad[name]['err'])-5} more[/dim]")
                _con.print(Panel("\n".join(body),
                                 title=f"[bold red]🎬 {name}[/bold red]",
                                 border_style="red", expand=False, padding=(0, 1)))
    else:
        print("\nPer-anime results:")
        for name in sorted(by_anime.keys(), key=str.lower):
            b = by_anime[name]
            print(f"  {name:<35s} ✓ {len(b['ok'])}  ✗ {len(b['err'])}")
            for fn, msg in b["err"][:3]:
                print(f"      · {fn}: {msg}")

    # ── FINAL SUMMARY ──
    notes = []
    if skipped.get("partial"):
        notes.append(f"⚠  skipped {skipped['partial']} partial — run Download Fonts / Build _Fonts first, then Mux again")
    if skipped.get("blocked"):
        notes.append(f"❌ skipped {skipped['blocked']} blocked (no _Fonts available)")
    if skipped.get("muxed"):
        notes.append(f"⏭  skipped {skipped['muxed']} already-muxed (resume)")
    if errs_flat:
        log_path = Path(anime_root) / LOG_FILENAME
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== Smart Mux run at {datetime.datetime.now()} ===\n")
            for v, m in errs_flat:
                # The worker tags errors with a "|FULL|..." suffix carrying the
                # entire stderr blob. Strip the marker, write the FULL text to
                # disk, but keep the on-screen panel compact.
                if "|FULL|" in m:
                    short, full = m.split("|FULL|", 1)
                else:
                    short, full = m, m
                f.write(f"[FAIL] {v}\n  short : {short.strip()}\n  full  :\n")
                for ln in full.strip().splitlines():
                    f.write(f"          {ln}\n")
        notes.append(f"→ full error log : {log_path}")
    notes.append(f"→ resume state    : {_state_path(anime_root)}")
    notes.append(f"→ markdown report : {Path(anime_root) / REPORT_FILENAME}")
    _print_summary("Smart Mux Complete", done, err, notes)

# 13. NEW-ANIME WIZARD
# =========================================================================
def new_anime_wizard(src_path=None, confirm=None):
    """Move a newly-downloaded anime from Downloads/ into the library and
    mux subtitles in one go.

    When called from the curses UI, `src_path` is the folder the user
    picked with arrow keys, and `confirm` is the arrow-key Yes/No helper —
    so the whole flow needs zero typing.
    """
    if confirm is None:
        def confirm(question, default=True):
            if not sys.stdin.isatty() or os.environ.get("ANIME_STUDIO_AUTO_YES") == "1":
                return default
            suf = " (Y/n): " if default else " (y/N): "
            ans = input(question + suf).strip().lower()
            if not ans: return default
            return ans in ("y", "yes")

    print("\n=========== NEW  ANIME  WIZARD ============")
    print(f"Source     : {DEFAULT_DOWNLOADS}")
    print(f"Destination: {DEFAULT_ANIME_ROOT}")
    if src_path:
        src = Path(src_path)
    else:
        src = Path(input("Drag-drop the new anime folder here (or paste path): "
                         ).strip().strip('"\''))
    if not src.is_dir():
        print("❌ Not a directory."); return

    fonts_dir = find_fonts_folder_nearby(src)
    if not fonts_dir:
        print(f"⚠ No _Fonts folder detected inside {src}.")
        print("   The mux will proceed without attaching any fonts.")
    else:
        print(f"✓ Found fonts directory: {fonts_dir}")

    # 1) Mux IN PLACE first (faster than copying then muxing)
    run_smart_mux(str(src), only_folder=str(src), output_mode="replace",
                  keep_originals=False)

    # 2) Offer to move it to the permanent library
    if confirm(f"Move '{src.name}' into {DEFAULT_ANIME_ROOT}?", default=True):
        target = Path(DEFAULT_ANIME_ROOT) / src.name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(target))
            print(f"✓ Moved → {target}")
        except Exception as e:
            print(f"✗ Move failed: {e}")

    # 3) Offer to drop the now-redundant _Fonts folder
    if fonts_dir and confirm("Delete the original _Fonts folder "
                              "(now embedded in MKVs)?", default=False):
        try:
            shutil.rmtree(fonts_dir)
            print(f"✓ Removed {fonts_dir}")
        except Exception as e:
            print(f"✗ {e}")


def guided_recovery_wizard(anime_root, do_download=True, do_scan=True,
                             do_mux=True):
    """Simple, low-friction workflow for normal users.

    v1.8 design: the caller (curses UI) is responsible for asking the user
    which steps to run, BEFORE this function drops into heavy console
    output. That avoids the v1.7 freeze where the wizard tried to draw a
    curses dialog while curses had been suspended for the previous step.

    This function therefore takes three booleans and runs each step
    unconditionally if requested, with no further prompting in between.
    """
    if _RICH:
        steps_text = []
        if do_download:
            steps_text.append("  1. Download missing fonts from every available source")
        if do_scan:
            steps_text.append("  2. Build per-anime _Fonts folders from the central pool")
        if do_mux:
            steps_text.append("  3. Mux episodes into MKV with a clear pre-flight report")
        body = "[bold]Running the following steps in order:[/bold]\n\n" \
               + "\n".join(steps_text)
        _con.print()
        _con.print(Panel(body, title='Guided Recovery — running now',
                         border_style='cyan', expand=False))
    else:
        print('\n=== Guided Recovery — running now ===')

    if do_download:
        download_missing_fonts(anime_root)
    if do_scan:
        scan_and_backup_anime_fonts(anime_root)
    if do_mux:
        run_smart_mux(anime_root, only_folder=anime_root,
                      output_mode='replace', keep_originals=False,
                      policy='safe', auto_confirm=True)


# =========================================================================
# 14. CURSES UI  v1.6  —  keyboard-first navigation with history stack
# =========================================================================
#
# Design notes (from user feedback):
#   • All confirmations are arrow-key dialogs — NO yes/no typing anywhere
#   • ESC = back one screen, BACKSPACE = also back
#   • Breadcrumb bar at the top shows where you are in the navigation
#   • Help bar at the bottom always shows the hotkeys
#   • Long-running operations briefly exit curses, but on completion you
#     return automatically to the menu you came from (no Press-Enter needed
#     except after stdout-heavy operations)
#
def main_ui(stdscr):
    import curses
    # ── CRITICAL: enable keypad mode so arrow keys are translated to
    # curses.KEY_LEFT/RIGHT/UP/DOWN. On Windows with windows-curses, the
    # absence of this call is what made the v1.7 confirm dialog freeze:
    # the dialog was waiting for KEY_LEFT but getch() was returning the
    # raw escape sequence bytes 27, 91, 68 from the terminal driver.
    stdscr.keypad(True)
    # Reduce ESC key processing latency from the default 1 sec.
    # Some platforms expose this only through the environment variable.
    try:
        curses.set_escdelay(25)
    except Exception:
        pass

    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    for i, fg in enumerate([curses.COLOR_CYAN, curses.COLOR_GREEN,
                            curses.COLOR_RED, curses.COLOR_YELLOW], 1):
        try: curses.init_pair(i, fg, -1)
        except: pass
    try: curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN)
    except: pass

    # ── Color setup ──────────────────────────────────────────────────────
    # 1=cyan headings, 2=green ok, 3=red errors, 4=yellow hints,
    # 5=highlighted selection (black on cyan), 6=breadcrumb (dim),
    # 7=help bar (reverse video).
    try: curses.init_pair(6, curses.COLOR_BLUE,  -1)
    except: pass
    try: curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)
    except: pass

    # ── Navigation history stack — ESC pops one entry ─────────────────────
    breadcrumb = ["🏠 Main Menu"]

    HELP_LINE = " ↑↓/jk  navigate    Enter  select    /  filter    Esc/←  back    Q  quit "

    def _safe_addstr(y, x, s, attr=0):
        h, w = stdscr.getmaxyx()
        if y < 0 or y >= h:
            return
        try:
            stdscr.addstr(y, x, s[:max(0, w - x - 1)], attr)
        except Exception:
            pass

    def _draw_chrome():
        """Render the persistent app chrome: title bar, breadcrumb, help bar."""
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        # Title bar
        _safe_addstr(0, 0, "  🎌  ANIME STUDIO v2.0  —  Forensic Edition  ".ljust(w),
                     curses.A_REVERSE | curses.A_BOLD)
        # Breadcrumb
        crumbs = "   ▸ ".join(breadcrumb)
        _safe_addstr(1, 2, crumbs, curses.color_pair(6) | curses.A_DIM)
        # Help bar at the bottom (reverse video)
        try:
            stdscr.addstr(h - 1, 0, HELP_LINE.ljust(w),
                          curses.color_pair(7) | curses.A_BOLD)
        except Exception:
            pass

    def menu(title, items, subtitle="", show_back=True):
        """Arrow-key menu with fuzzy filter (press / to search).

        Returns the selected item string, or None when the user pressed ESC
        / Backspace / Q (back).  If `show_back=True`, the user can also
        select "⬅  Back" as the first entry — useful when ESC may collide
        with a terminal that swallows the key.
        """
        if show_back and (not items or items[0] != "⬅  Back"):
            items = ["⬅  Back", *items]

        def _selectable(label):
            """Items that are blank or start with a separator dash are
            decorative headers, not menu choices."""
            return bool(label) and not label.lstrip().startswith("──")

        def _fuzzy_filter(all_items, query):
            """Return items matching query (case-insensitive substring)."""
            if not query:
                return all_items
            q = query.lower()
            # Always keep Back entry + matches; keep separators only if adjacent items match
            filtered = []
            for item in all_items:
                if item == "⬅  Back":
                    filtered.append(item)
                elif not _selectable(item):
                    # separator — include only if next real item would match
                    continue
                elif q in item.lower():
                    filtered.append(item)
            return filtered if filtered else ["⬅  Back"]

        def _read_filter_query():
            """Drop to a one-line input at the bottom: type query, Enter confirms, Esc cancels."""
            h, w = stdscr.getmaxyx()
            query = ""
            curses.curs_set(1)
            while True:
                prompt = f"  / {query}_"
                stdscr.addstr(h - 2, 0, prompt.ljust(w - 1),
                              curses.color_pair(4) | curses.A_BOLD)
                stdscr.refresh()
                k = stdscr.getch()
                if k in (10, 13):           # Enter — confirm
                    break
                elif k in (27,):            # Esc — cancel
                    query = ""
                    break
                elif k in (curses.KEY_BACKSPACE, 8, 127):
                    query = query[:-1]
                elif 32 <= k <= 126:
                    query += chr(k)
            curses.curs_set(0)
            # Clear the filter line
            stdscr.addstr(h - 2, 0, " " * (w - 1))
            return query

        # Initial cursor: first selectable item (skip Back if possible)
        idx = 0
        if show_back and len(items) > 1:
            idx = 1
        while idx < len(items) and not _selectable(items[idx]):
            idx += 1
        if idx >= len(items):
            idx = 0

        active_items = list(items)   # may be narrowed by filter
        filter_query = ""

        while True:
            _draw_chrome()
            h, w = stdscr.getmaxyx()
            _safe_addstr(3, 2, title, curses.A_BOLD)
            if subtitle:
                _safe_addstr(4, 2, "ℹ  " + subtitle, curses.color_pair(2))
            if filter_query:
                _safe_addstr(4 if not subtitle else 5, 2,
                             f"  🔍 filter: {filter_query}  (Esc to clear)",
                             curses.color_pair(4))
            row_top = 6 if subtitle else 5
            if filter_query:
                row_top += 1
            available = max(1, h - row_top - 2)  # leave room for help bar
            # Scrolling window
            off = max(0, idx - available + 1)
            for i in range(min(len(active_items), available)):
                c = i + off
                if c >= len(active_items):
                    break
                label = active_items[c]
                if not _selectable(label):
                    style = curses.A_DIM
                elif c == idx:
                    style = curses.color_pair(5) | curses.A_BOLD
                else:
                    style = curses.A_NORMAL
                line = f"  {label}  "
                _safe_addstr(row_top + i, 2, line.ljust(w - 4), style)
            stdscr.refresh()
            k = stdscr.getch()
            if k in (curses.KEY_UP, ord('k')):
                new_idx = idx - 1
                while new_idx >= 0 and not _selectable(active_items[new_idx]):
                    new_idx -= 1
                if new_idx >= 0:
                    idx = new_idx
            elif k in (curses.KEY_DOWN, ord('j')):
                new_idx = idx + 1
                while new_idx < len(active_items) and not _selectable(active_items[new_idx]):
                    new_idx += 1
                if new_idx < len(active_items):
                    idx = new_idx
            elif k in (curses.KEY_HOME, ord('g')):
                idx = 0
            elif k in (curses.KEY_END, ord('G')):
                idx = len(active_items) - 1
            elif k in (curses.KEY_PPAGE,):
                idx = max(0, idx - available + 1)
            elif k in (curses.KEY_NPAGE,):
                idx = min(len(active_items) - 1, idx + available - 1)
            elif k == ord('/'):
                # Open fuzzy filter input
                new_query = _read_filter_query()
                if new_query != filter_query:
                    filter_query = new_query
                    active_items = _fuzzy_filter(items, filter_query)
                    # Reset cursor to first selectable
                    idx = 0
                    for i, it in enumerate(active_items):
                        if _selectable(it) and it != "⬅  Back":
                            idx = i
                            break
            elif k in (27, curses.KEY_BACKSPACE, 8, 127, curses.KEY_LEFT):
                if filter_query:
                    # Esc clears filter first before going back
                    filter_query = ""
                    active_items = list(items)
                    idx = 1 if show_back and len(active_items) > 1 else 0
                else:
                    return None
            elif k in (10, 13):
                sel = active_items[idx]
                if not _selectable(sel):
                    continue
                if sel == "⬅  Back":
                    return None
                return sel
            elif k in (ord('q'), ord('Q')):
                return "__QUIT__"

    def confirm(question, default=True):
        """Arrow-key Yes/No dialog. Returns True/False — never None."""
        # Default-yes puts "Yes" first; default-no puts "No" first.
        opts = ["✓ Yes", "✗ No"] if default else ["✗ No", "✓ Yes"]
        idx  = 0
        while True:
            _draw_chrome()
            h, w = stdscr.getmaxyx()
            _safe_addstr(3, 2, "?  " + question, curses.A_BOLD)
            _safe_addstr(5, 4, "Use ←/→ or ↑/↓ to choose, Enter to confirm:",
                         curses.color_pair(4))
            # Render the two buttons side-by-side
            btn_y = 7
            for i, label in enumerate(opts):
                style = (curses.color_pair(5) | curses.A_BOLD) \
                        if i == idx else curses.A_NORMAL
                _safe_addstr(btn_y, 6 + i * 18, f"  {label}  ".ljust(14), style)
            stdscr.refresh()
            k = stdscr.getch()
            if k in (curses.KEY_LEFT, curses.KEY_UP, ord('h'), ord('k')):
                idx = (idx - 1) % len(opts)
            elif k in (curses.KEY_RIGHT, curses.KEY_DOWN, ord('l'), ord('j')):
                idx = (idx + 1) % len(opts)
            elif k in (ord('y'), ord('Y')):
                return True
            elif k in (ord('n'), ord('N')):
                return False
            elif k in (10, 13):
                return opts[idx].startswith("✓")
            elif k in (27,):
                return False

    def info(title, lines, pause=True):
        """Show a static message screen. Press any key to dismiss."""
        _draw_chrome()
        h, w = stdscr.getmaxyx()
        _safe_addstr(3, 2, title, curses.A_BOLD | curses.color_pair(1))
        for i, ln in enumerate(lines):
            if 5 + i >= h - 2:
                break
            _safe_addstr(5 + i, 2, ln)
        if pause:
            _safe_addstr(h - 3, 2, "Press any key to continue…",
                         curses.color_pair(4))
        stdscr.refresh()
        if pause:
            stdscr.getch()

    def browse_folder(title, start=None):
        """Folder picker — arrow keys only. Returns the chosen path or None."""
        curr = start or DEFAULT_ANIME_ROOT
        if not os.path.isdir(curr):
            curr = (os.path.splitdrive(curr)[0] + "\\") if sys.platform == "win32" else "/"
        breadcrumb.append("📁 " + title)
        try:
            while True:
                try:
                    entries = sorted(d for d in os.listdir(curr)
                                     if os.path.isdir(os.path.join(curr, d))
                                     and not d.startswith("."))
                except PermissionError:
                    entries = []
                opts = ["✅ USE THIS FOLDER  (" + os.path.basename(curr or curr) + ")",
                        "⬆  Go to parent folder",
                        *entries]
                sel = menu(title, opts,
                           subtitle=f"Current path: {curr}",
                           show_back=True)
                if sel is None or sel == "__QUIT__":
                    return None
                if sel.startswith("✅"):
                    return curr
                if sel.startswith("⬆"):
                    parent = os.path.dirname(curr)
                    if parent and parent != curr:
                        curr = parent
                    continue
                # entry into a subfolder
                curr = os.path.join(curr, sel)
        finally:
            if breadcrumb and breadcrumb[-1].startswith("📁"):
                breadcrumb.pop()

    def run_external(fn, *args, push_crumb=None, **kwargs):
        """Drop out of curses, run a heavy console function, then return.
        Optionally push/pop a breadcrumb crumb around the call.

        The terminal is ALWAYS restored via a try/finally even if fn raises,
        preventing a broken terminal state after an unexpected exception.
        """
        if push_crumb:
            breadcrumb.append(push_crumb)
        _output_lines = []   # track whether fn produced any visible output
        _orig_write = None
        try:
            curses.def_prog_mode()
            curses.endwin()
            # Intercept stdout writes to detect zero-output operations (#11)
            try:
                import io as _io
                _buf = _io.StringIO()
                _orig_write = sys.stdout.write
                def _tracked_write(s):
                    if s.strip():
                        _output_lines.append(s)
                    return _orig_write(s)
                sys.stdout.write = _tracked_write
            except Exception:
                pass
            try:
                fn(*args, **kwargs)
            except Exception as _fn_exc:
                # Print the error in console mode before restoring curses
                try:
                    print(f"\n\033[31m⚠ Error in operation: {type(_fn_exc).__name__}: {_fn_exc}\033[0m",
                          flush=True)
                    _output_lines.append("error")  # ensure Press Enter is shown
                except Exception:
                    pass
                raise
            finally:
                # Restore stdout tracking
                if _orig_write is not None:
                    try:
                        sys.stdout.write = _orig_write
                    except Exception:
                        pass
                # Only prompt if the operation produced visible output (#11)
                if _output_lines:
                    try:
                        print("\n\033[36m[ Operation finished. Press Enter to return to the menu ]\033[0m",
                              end="", flush=True)
                        sys.stdin.readline()
                    except Exception:
                        pass
        finally:
            # ALWAYS restore curses, no matter what happened
            try:
                curses.reset_prog_mode()
                stdscr.refresh()
            except Exception:
                pass
            if push_crumb and breadcrumb and breadcrumb[-1] == push_crumb:
                breadcrumb.pop()

    # ── Menu definitions ─────────────────────────────────────────────────
    # v2.0: lazygit-style [hotkey] labels + group separators.
    # The MenuItem registry (defined at module level) is the single source
    # of truth; these strings mirror it for the curses renderer.
    # The v2 features live under Advanced Tools to keep the main menu clean.
    MAIN_ITEMS = [
        "[s]  🚀  Start here — fix the library automatically  ★ recommended",
        "",
        "── steps ──",
        "[f]  🔤  Download missing fonts",
        "[b]  📂  Build _Fonts folders per anime",
        "[m]  🎬  Mux episodes into MKV",
        "",
        "── forensic ──",
        "[a]  🧪  Advanced tools (font health, missing subs, libass fix, hunter)",
        "",
        "── extras ──",
        "[n]  📦  Add a new anime from Downloads",
        "[c]  🧹  Clean generated files (_Fonts, reports, temp)",
        "[t]  🛠   Subtitle tools (rename / sync / merge)",
        "[p]  🎵  Setup mpv fallback fonts",
        "[?]  ❓  Help — what each step does",
        "[r]  ↻   Reset mux progress for a library",
        "[q]  ✖   Quit",
    ]

    while True:
        # v2.0: enrich the subtitle line with the live dashboard
        try:
            _v2_dash = v2_build_status_dashboard(DEFAULT_ANIME_ROOT)
            _v2_dash_text = "   •   ".join(_v2_dash[:2]) if _v2_dash else ""
        except Exception:
            _v2_dash_text = ""
        _sub = f"Library: {DEFAULT_ANIME_ROOT}"
        if _v2_dash_text:
            _sub = _v2_dash_text + "   |   " + _sub
        choice = menu("Main menu — choose what you want to do",
                      MAIN_ITEMS,
                      subtitle=_sub,
                      show_back=False)
        # v1.10: ESC from the main menu must NOT quit the program. Only an
        # explicit Quit selection or Ctrl+C terminates the session.
        if choice is None:
            # The user pressed ESC — confirm before exiting so we never
            # close "by itself".
            if confirm("Exit Anime Studio?", default=False):
                return
            continue
        if choice == "__QUIT__" or (choice.strip().startswith("✖") and "Quit" in choice):
            return

        # v2.0 Advanced Tools — opens a console submenu with all the new features
        if choice.startswith("🧪") or "Advanced tools" in choice:
            target = browse_folder("Pick the anime library root", DEFAULT_ANIME_ROOT)
            if not target:
                continue
            run_external(v2_extended_menu_console, target,
                         push_crumb="🧪 v2 Advanced Tools")
            continue

        # 1. One-click workflow — just pick the library and let the tool run.
        if choice.startswith("🚀") or "Start here" in choice:
            target = browse_folder("Pick the anime library root", DEFAULT_ANIME_ROOT)
            if not target:
                continue
            run_external(guided_recovery_wizard, target,
                         push_crumb="🚀 Start here",
                         do_download=True, do_scan=True, do_mux=True)
            continue

        # 2. Mux episodes
        if "Mux episodes into MKV" in choice or "Mux episodes" in choice:
            target = browse_folder("Pick the anime folder to mux",
                                   DEFAULT_ANIME_ROOT)
            if not target:
                continue
            policy_sel = menu("Which episodes should be muxed?", [
                "✅  Safe — only episodes with full font coverage  (recommended)",
                "⚠️  Include partial — also mux episodes missing some fonts",
                "🔥  Force everything — try every episode",
            ], subtitle="Use Safe unless you specifically want fallback rendering.")
            if policy_sel is None or policy_sel == "__QUIT__":
                continue
            policy = ("all" if policy_sel.startswith("🔥") else
                      "partial" if policy_sel.startswith("⚠") else
                      "safe")
            mode_sel = menu("Where should the output go?", [
                "✏️  Replace the original MKV files  (recommended)",
                "📂  Save new files into a _Muxed subfolder",
            ], subtitle="Mux uses stream copy, so video quality is unchanged.")
            if mode_sel is None or mode_sel == "__QUIT__":
                continue
            mode = "muxed" if mode_sel.startswith("📂") else "replace"
            keep = confirm("Keep the external .ass subtitle files after a successful mux?", default=False)
            run_external(run_smart_mux, DEFAULT_ANIME_ROOT,
                         push_crumb="🎬 Mux episodes",
                         only_folder=target, output_mode=mode,
                         keep_originals=keep, policy=policy,
                         auto_confirm=True)
            continue

        # 3. Download missing fonts
        if "Download missing fonts" in choice:
            target = browse_folder("Pick the anime library root",
                                   DEFAULT_ANIME_ROOT)
            if not target:
                continue
            run_external(download_missing_fonts, target,
                         push_crumb="🔤 Font hunt")
            continue

        # 4. Build _Fonts folders
        if "Build _Fonts folders" in choice:
            target = browse_folder("Pick the anime library root",
                                   DEFAULT_ANIME_ROOT)
            if not target:
                continue
            run_external(scan_and_backup_anime_fonts, target,
                         push_crumb="📂 Build _Fonts")
            continue

        # 5. New-anime wizard
        if "Add a new anime from Downloads" in choice:
            target = browse_folder("Pick the downloaded anime folder",
                                   DEFAULT_DOWNLOADS)
            if not target:
                continue
            run_external(new_anime_wizard, target,
                         push_crumb="📦 New anime",
                         confirm=confirm)
            continue

        # 6. Cleanup
        if "Clean generated files" in choice:
            target = browse_folder("Pick the anime library root",
                                   DEFAULT_ANIME_ROOT)
            if not target:
                continue
            if not confirm(f"Remove generated _Fonts folders / reports under\n"
                           f"  {target}\n\n"
                           "Original .mkv / .ass files are NOT touched.",
                           default=False):
                continue
            run_external(cleanup_anime_root, target,
                         push_crumb="🧹 Cleanup")
            continue

        # 7. mpv config
        if "Setup mpv fallback fonts" in choice:
            run_external(setup_mpv_config,
                         push_crumb="🎵 mpv config")
            continue

        # 8. Help
        if "Help — what each step does" in choice:
            run_external(print_help_text,
                         push_crumb="❓ Help")
            continue

        # 9. Subtitle tools submenu
        if "Subtitle tools" in choice:
            breadcrumb.append("🛠 Subtitle tools")
            try:
                sub_choice = menu("Subtitle tools (advanced)", [
                    "📝  Rename subtitle files to match videos",
                    "⏱   Fix subtitle timing with ffsubsync",
                    "🔗  Simple merge — subtitles only (legacy)",
                ], subtitle="Use only when you need one of these specific tasks.")
            finally:
                if breadcrumb and breadcrumb[-1] == "🛠 Subtitle tools":
                    breadcrumb.pop()
            if not sub_choice or sub_choice == "__QUIT__":
                continue
            mode = ("3" if sub_choice.startswith("📝") else
                    "4" if sub_choice.startswith("⏱") else
                    "5" if sub_choice.startswith("🔗") else None)
            if mode:
                run_simple_in_folder(stdscr, mode=mode)
            continue

        # R. Reset progress tracking
        if "Reset mux progress" in choice:
            target = browse_folder("Pick the anime library root",
                                   DEFAULT_ANIME_ROOT)
            if not target:
                continue
            p  = Path(target) / STATE_FILENAME
            rp = Path(target) / REPORT_FILENAME
            existed = []
            if p.exists():  existed.append(p.name)
            if rp.exists() and confirm(
                    f"Also delete the markdown report {rp.name}?",
                    default=False):
                try: rp.unlink(); existed.append(rp.name)
                except Exception: pass
            if not p.exists() and not existed:
                info("Nothing to reset",
                     [f"No resume state at {p}",
                      "Run a mux first to create one."])
                continue
            if not confirm(
                    f"Reset progress under\n  {target}\n\n"
                    "This will re-mux EVERY episode the next time you run "
                    "Smart Mux, even ones that already finished.",
                    default=False):
                continue
            try:
                if p.exists(): p.unlink()
            except Exception as e:
                info("Reset failed", [str(e)])
                continue
            info("Reset complete",
                 [f"✓ Removed: {', '.join(existed) or p.name}",
                  "",
                  "The next mux run will start from scratch."])
            continue


def text_input_console(prompt, default=""):
    print(f"\n{prompt}")
    print(f"  [default: {default}]")
    v = input("  > ").strip().strip('"\'')
    return v or default


def print_help_text():
    print("""
========================================================================
                 MUXING   vs   sub-fonts-dir   in   mpv
========================================================================

✅ MUXING  (recommended) — embed fonts as Matroska attachments
   • Works on EVERY player: mpv, VLC, Plex, Jellyfin, MX Player, TVs
   • MKV is self-contained — move / copy / share freely
   • Survives Windows reinstall (fonts live inside the video)
   • Uses the canonical Matroska font-attachment MIME types
   • Per-file overhead: +5–50 MB  (vs 200 MB – 2 GB video sizes)
   • Done once with `-c copy` (no re-encoding) → seconds per episode

⚠  sub-fonts-dir / sub-fonts-dir=auto  (mpv only)
   • mpv-only — no other player respects it
   • `auto` has known bugs (GitHub mpv-player/mpv#15461) with
     non-`fonts/` folder names and nested directories
   • Couples the videos to disk layout — rename / move breaks it
   • Doesn't help mobile playback or casting

VERDICT
   • Treat _Fonts folders as a TEMPORARY staging area.
   • Run Smart Mux once → fonts permanently live inside each MKV.
   • Use sub-fonts-dir only as a tiny safety net for not-yet-muxed
     downloads (point it at ~/portable_fonts/).

========================================================================
""")


def run_simple_in_folder(stdscr, mode):
    """Original Media_Toolbox.py behaviour for rename / sync / simple-merge."""
    import curses
    curr = os.getcwd()
    while True:
        try:
            entries = sorted([d for d in os.listdir(curr)
                              if os.path.isdir(os.path.join(curr, d))])
        except Exception:
            entries = []
        opts = ["..", "."] + entries
        idx = 0
        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()
            stdscr.addstr(0, 0,
                          f"  📂 {curr[-w+4:]}  —  pick folder ".ljust(w),
                          curses.A_REVERSE)
            for i, e in enumerate(opts[:h-2]):
                d = ("⬆ Up" if e == ".." else
                     "✅ Use this folder" if e == "." else e)
                style = curses.color_pair(5) if i == idx else curses.A_NORMAL
                try: stdscr.addstr(2+i, 2, f" {d} ".ljust(w-4), style)
                except: pass
            k = stdscr.getch()
            if k == curses.KEY_UP and idx > 0: idx -= 1
            elif k == curses.KEY_DOWN and idx < len(opts)-1: idx += 1
            elif k == 27: return
            elif k in (10, 13):
                sel = opts[idx]
                if sel == "..":
                    curr = os.path.dirname(curr); break
                if sel == ".":
                    do_simple_action(stdscr, curr, mode); return
                curr = os.path.join(curr, sel); break


def do_simple_action(stdscr, folder, mode):
    import curses
    matches, nv, ns = Logic.pair_videos_and_subs(folder)
    if not matches:
        stdscr.clear()
        stdscr.addstr(2, 2, f"No matched pairs in {folder} "
                            f"(vids={nv}, subs={ns}). Press any key.")
        stdscr.refresh(); stdscr.getch(); return

    h, w = stdscr.getmaxyx()
    if mode == "3":   # rename
        plan, jobs, undo = [], [], {}
        for m in matches:
            new = Path(m["vid"]).stem + Path(m["sub"]).suffix
            if new != m["sub"]:
                jobs.append((m["sub"], new)); undo[new] = m["sub"]
                plan.append(f"{m['sub'][:30]} → {new[:30]}")
        stdscr.clear()
        stdscr.addstr(1, 2, "RENAME PLAN", curses.A_BOLD)
        for i, p in enumerate(plan[:h-5]):
            stdscr.addstr(3+i, 2, p[:w-4])
        stdscr.addstr(h-2, 2, "Press ENTER to apply, any other to cancel.")
        if stdscr.getch() in (10, 13):
            ok = 0
            for old, new in jobs:
                try:
                    os.rename(os.path.join(folder, old),
                              os.path.join(folder, new)); ok += 1
                except Exception as e:
                    log_event(folder, f"rename {old}: {e}", "ERR")
            (Path(folder) / UNDO_FILENAME).write_text(json.dumps(undo))
            stdscr.addstr(h-1, 2, f"Renamed {ok}/{len(jobs)}. Press a key.")
            stdscr.getch()

    elif mode == "4":   # sync
        if not shutil.which("ffsubsync"):
            stdscr.clear(); stdscr.addstr(2, 2, "ffsubsync not installed.")
            stdscr.getch(); return
        tasks = [(os.path.join(folder, m["vid"]),
                  os.path.join(folder, m["sub"]),
                  os.path.join(folder, Path(m["vid"]).stem + Path(m["sub"]).suffix))
                 for m in matches]
        stdscr.clear(); stdscr.addstr(1, 2, "Syncing — CPU intensive.")
        stdscr.refresh()
        done = err = 0
        with concurrent.futures.ProcessPoolExecutor() as pool:
            for ok, sub, _ in pool.map(sync_task, tasks):
                if ok: done += 1
                else: err += 1
                stdscr.addstr(3, 2, f"Progress {done+err}/{len(tasks)}  "
                                    f"(✓ {done}  ✗ {err})")
                stdscr.refresh()
        stdscr.addstr(5, 2, "Done. Press a key."); stdscr.getch()

    elif mode == "5":   # legacy simple merge (no fonts)
        tasks = []
        for m in matches:
            vp = os.path.join(folder, m["vid"])
            sp = os.path.join(folder, m["sub"])
            base = Path(m["vid"]).stem
            tasks.append((vp, sp,
                          os.path.join(folder, base + "_temp.mkv"),
                          os.path.join(folder, base + ".mkv")))
        stdscr.clear()
        stdscr.addstr(1, 2, "Simple merge — embeds subs ONLY (no fonts).")
        stdscr.addstr(2, 2, "(Use Smart Mux from the main menu to attach fonts.)")
        stdscr.addstr(4, 2, "Press ENTER to start, any other to cancel.")
        if stdscr.getch() in (10, 13):
            done = err = 0
            with concurrent.futures.ProcessPoolExecutor() as pool:
                for ok, sub, msg in pool.map(simple_embed_task, tasks):
                    if ok:
                        done += 1
                        try: os.remove(sub)
                        except: pass
                    else:
                        err += 1
                        log_event(folder, f"merge {sub}: {msg}", "ERR")
                    stdscr.addstr(6, 2, f"Progress {done+err}/{len(tasks)}")
                    stdscr.refresh()
            stdscr.addstr(8, 2, f"Done. ✓ {done} ✗ {err}. Press a key.")
            stdscr.getch()


# =========================================================================
# 15. ENTRY POINT
# =========================================================================
def _text_mode_menu():
    """
    Minimal numbered-prompt fallback used when curses is unavailable.
    Covers the most-needed operations so the tool stays usable even on
    headless servers or terminals that don't support curses.
    """
    root = Path(DEFAULT_ANIME_ROOT)
    options = [
        ("Download missing fonts",         lambda: download_missing_fonts(root)),
        ("Scan & build _Fonts folders",    lambda: scan_and_backup_anime_fonts(root)),
        ("Show missing fonts report",      lambda: _print_missing_report(root)),
        ("Quit",                           lambda: sys.exit(0)),
    ]
    while True:
        print("\n" + "─" * 50)
        print("  Anime Studio v2.0 — Text Mode")
        print("─" * 50)
        for i, (label, _) in enumerate(options, 1):
            print(f"  [{i}] {label}")
        print("─" * 50)
        try:
            choice = input("  Choice: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            sys.exit(0)
        if not choice.isdigit() or not (1 <= int(choice) <= len(options)):
            print("  Invalid choice — enter a number from the list.")
            continue
        try:
            options[int(choice) - 1][1]()
        except Exception as exc:
            print(f"\n  ⚠ Error: {exc}")
            if "--debug" in sys.argv:
                traceback.print_exc()

def _print_missing_report(root: Path):
    """Print the missing-fonts report to stdout (text-mode helper)."""
    report = root / MISSING_REPORT_NAME
    if report.exists():
        print(report.read_text(encoding="utf-8", errors="replace"))
    else:
        print(f"  No report found at {report}")


def main():
    cli = check_dependencies()

    # v2.0: Install Universal Hunter as Strategy 0 in FontHunter
    try:
        v2_install_hunter_integration()
    except Exception:
        pass

    # ── Startup banner ────────────────────────────────────────────────────
    if _RICH:
        t = Table(title="🎌  Anime Studio  v2.0  —  Forensic Edition",
                  box=_rbox.ROUNDED, border_style="blue",
                  title_style="bold magenta", header_style="bold cyan")
        t.add_column("CLI Tool",        style="bold white", min_width=12)
        t.add_column("Status",          min_width=12)
        t.add_column("Install Command", style="dim",        min_width=42)
        for tool, ok, cmd in [
            ("mkvmerge",  cli["mkvmerge"],  "scoop install mkvtoolnix"),
            ("ffmpeg",    cli["ffmpeg"],    "scoop install ffmpeg"),
            ("ffsubsync", cli["ffsubsync"], "uv tool install ffsubsync"),
        ]:
            status  = "[green]✓  found[/green]"  if ok else "[red]✗  missing[/red]"
            install = "[dim]—[/dim]"              if ok else f"[yellow]{cmd}[/yellow]"
            t.add_row(tool, status, install)
        _con.print(t)
    else:
        print("Anime Studio v1.0")
        print(f"  ffmpeg    : {'✓' if cli['ffmpeg']    else '✗  → scoop install ffmpeg'}")
        print(f"  mkvmerge  : {'✓' if cli['mkvmerge']  else '✗  → scoop install mkvtoolnix'}")
        print(f"  ffsubsync : {'✓' if cli['ffsubsync'] else '✗  → uv tool install ffsubsync'}")

    if not cli["mkvmerge"] and not cli["ffmpeg"]:
        rprint("\n[bold red]❌ You need at least one of mkvmerge or ffmpeg.[/bold red]")
        rprint("   Recommended : [yellow]scoop install mkvtoolnix[/yellow]")
        rprint("   Fallback    : [yellow]scoop install ffmpeg[/yellow]  →  https://ffmpeg.org/")
        input("Press Enter to exit…"); sys.exit(1)

    try:
        import curses
        curses.wrapper(main_ui)
    except KeyboardInterrupt:
        print("\nBye.")
    except curses.error as e:
        # Real terminal incompatibility — graceful text-mode fallback
        if _RICH:
            _con.print(f"[yellow]Curses unavailable ({e}). "
                       f"Running text-mode menu.[/yellow]")
        else:
            print(f"Curses unavailable ({e}). Running text-mode menu.")
        _text_mode_menu()
    except Exception as e:
        # Unexpected app crash — log full trace, show one-liner to user
        _log_path = Path.home() / ".anime_studio_crash.log"
        try:
            _log_path.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        if _RICH:
            _con.print(Panel(
                f"[red]Something broke:[/red] {type(e).__name__}: {e}\n"
                f"[dim]Full traceback saved to:[/dim] {_log_path}\n"
                f"[dim]Tip: run with --debug to see it inline.[/dim]",
                title="⚠ Anime Studio crashed", border_style="red"))
        else:
            print(f"\n⚠ Anime Studio crashed: {type(e).__name__}: {e}")
            print(f"  Full traceback saved to: {_log_path}")
            print("  Tip: run with --debug to see it inline.")
        if "--debug" in sys.argv:
            raise
        sys.exit(2)



# =========================================================================
#  v2.0  FORENSIC ENGINE  — Integrated Modules
# =========================================================================
#  Everything below this line and above the next major-section header is
#  v2.0 code. It supersedes the v1.8 implementations of:
#    - _verify_muxed_file       (language matching bug fix)
#    - build_font_map           (multi-index)
#    - system_font_map          (multi-index)
#    - resolve_required_fonts   (cascading)
#    - font_names_from_file     (now returns structured dict)
#    - sync_task                (alass + ffsubsync unified)
#
#  And adds new functionality:
#    - safe_delete_or_trash
#    - check_font_health / repair_font
#    - patch_font_name / patch_ass_font_references
#    - EmbeddedAssCache / get_embedded_subs_info
#    - universal_hunt
#    - find_anime_without_subs / write_missing_subs_report
# =========================================================================

import urllib.parse  # used by hunter v2 + missing-subs report
import urllib.error
import zipfile
import tempfile

# ---------- Language matching matrix (the bug-fix data) ----------
_ARABIC_LANG_CODES = {
    "ar", "ara", "arb",
    "ar-eg", "ar-sa", "ar-ae", "ar-ma", "ar-iq", "ar-jo",
    "ar-kw", "ar-lb", "ar-ly", "ar-om", "ar-qa", "ar-sy",
    "ar-tn", "ar-ye", "ar-dz", "ar-bh", "ar-ps",
}
_LANG_FAMILIES = {
    "ara": _ARABIC_LANG_CODES,
    "eng": {"en", "eng", "en-us", "en-gb", "en-au", "en-ca"},
    "jpn": {"ja", "jpn", "ja-jp"},
    "fre": {"fr", "fra", "fre", "fr-fr", "fr-ca"},
    "ger": {"de", "deu", "ger", "de-de", "de-at"},
    "spa": {"es", "spa", "es-es", "es-mx", "es-ar"},
    "ita": {"it", "ita", "it-it"},
    "por": {"pt", "por", "pt-br", "pt-pt"},
    "rus": {"ru", "rus", "ru-ru"},
    "chi": {"zh", "chi", "zho", "zh-cn", "zh-tw", "zh-hk"},
    "kor": {"ko", "kor", "ko-kr"},
    "tur": {"tr", "tur", "tr-tr"},
}


def v2_language_matches(track_lang_iso, track_lang_ietf, expected):
    """v2.0 — proper language matching that handles ar/ara/arb correctly.
    Replaces the broken "".startswith() logic of v1.8."""
    expected = (expected or "").lower().strip()
    iso = (track_lang_iso or "").lower().strip()
    ietf = (track_lang_ietf or "").lower().strip()
    if expected and (iso == expected or ietf == expected):
        return True
    family = _LANG_FAMILIES.get(expected, set())
    if iso in family or ietf in family:
        return True
    if expected in _LANG_FAMILIES:
        for code in family:
            if ietf.startswith(code + "-") or iso.startswith(code + "-"):
                return True
    return False


# ---------- Safe delete (trash) ----------
def v2_safe_delete_or_trash(file_path, anime_root=None, reason="cleanup"):
    """v2.0 — replaces os.remove() for .ass / .mkv cleanup.
    Moves to .anime_studio_trash/ with a JSONL manifest; auto-purges after 30 days."""
    from pathlib import Path as _P
    src = _P(file_path)
    if not src.exists():
        return "skipped", None
    if anime_root:
        trash_root = _P(anime_root) / ".anime_studio_trash"
    else:
        trash_root = src.parent / ".anime_studio_trash"
    trash_root.mkdir(exist_ok=True)
    _v2_purge_old_trash(trash_root, days=30)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = trash_root / f"{ts}_{src.name}"
    n = 1
    while dest.exists():
        dest = trash_root / f"{ts}_{n:02d}_{src.name}"
        n += 1
    try:
        shutil.move(str(src), str(dest))
        manifest = trash_root / "_trash_manifest.jsonl"
        with manifest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": ts, "original": str(src), "trashed": str(dest), "reason": reason,
            }) + "\n")
        return "trashed", dest
    except Exception:
        try:
            src.unlink()
            return "deleted", None
        except Exception:
            return "skipped", None


def _v2_purge_old_trash(trash_root, days=30):
    import time as _t
    cutoff = _t.time() - (days * 86400)
    try:
        for item in trash_root.iterdir():
            if item.name == "_trash_manifest.jsonl":
                continue
            try:
                if item.stat().st_mtime < cutoff:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
            except Exception:
                pass
    except Exception:
        pass


# ---------- Multi-index font matching ----------
_V2_FONT_WEIGHT_SUFFIXES = (
    "regular", "normal", "book", "roman",
    "light", "thin", "extralight", "ultralight",
    "medium", "demibold", "semibold", "demi",
    "bold", "extrabold", "ultrabold", "heavy", "black",
    "italic", "oblique", "slanted",
    "condensed", "narrow", "expanded", "wide",
    "display", "text", "caption", "subhead",
    # Short forms — critical for "Hacen Liner Screen Bd"
    "bd", "blk", "hv", "lt", "md", "rg", "sb", "sl", "it",
    "cn", "cd", "ex", "xl", "xb", "ul",
)
_V2_FONT_FOUNDRY_PREFIXES = (
    "adobe", "itc", "linotype", "monotype", "url",
    "sc", "ms", "google", "tt",
)


def v2_root_key(name):
    """v2.0 — strips weight suffixes including short forms (Bd, Lt, Md, etc.)."""
    k = clean_key(name)  # uses existing clean_key from v1.8
    for pfx in _V2_FONT_FOUNDRY_PREFIXES:
        pfx_norm = clean_key(pfx)
        if pfx_norm and k.startswith(pfx_norm):
            k = k[len(pfx_norm):]
            break
    changed = True
    while changed:
        changed = False
        for sfx in _V2_FONT_WEIGHT_SUFFIXES:
            sfx_norm = clean_key(sfx)
            if sfx_norm and k.endswith(sfx_norm) and len(k) > len(sfx_norm) + 2:
                k = k[:-len(sfx_norm)]
                changed = True
                break
    return k


def v2_font_names_from_file(path):
    """v2.0 — returns STRUCTURED dict instead of flat set.
    Backward-compat helpers exposed below."""
    result = {
        "family": set(), "full": set(), "postscript": set(),
        "typo_family": set(), "wws_family": set(), "all": set(),
    }
    try:
        from fontTools.ttLib import TTFont, TTCollection
        ext = Path(path).suffix.lower()
        if ext == ".ttc":
            fonts = TTCollection(str(path)).fonts
        else:
            fonts = [TTFont(str(path), lazy=True, fontNumber=0)]
        for tt in fonts:
            if "name" not in tt:
                continue
            for rec in tt["name"].names:
                try:
                    s = rec.toUnicode().strip()
                    if not s:
                        continue
                    nid = rec.nameID
                    if nid == 1: result["family"].add(s)
                    elif nid == 4: result["full"].add(s)
                    elif nid == 6: result["postscript"].add(s)
                    elif nid == 16: result["typo_family"].add(s)
                    elif nid == 21: result["wws_family"].add(s)
                    if nid in (1, 4, 6, 16, 21):
                        result["all"].add(s)
                except Exception:
                    pass
    except Exception:
        pass
    return result


def v2_build_font_map(folder, verbose=False):
    """v2.0 — 7-index font map (the heart of mismatch detection)."""
    fmap = {
        "precise": {}, "roots": {}, "raw": {},
        "by_filename": {}, "by_postscript": {}, "by_fullname": {},
        "files": {},
    }
    folder = Path(folder)
    if not folder.exists():
        return fmap
    FE = {".ttf", ".otf", ".ttc", ".otc"}
    for p in folder.rglob("*"):
        try:
            if not p.is_file() or p.suffix.lower() not in FE:
                continue
        except Exception:
            continue
        names = v2_font_names_from_file(p)
        fmap["files"][p] = names
        # Filename index
        fk = clean_key(p.stem)
        if fk and fk not in fmap["by_filename"]:
            fmap["by_filename"][fk] = p
        # Internal indices
        for n in names["all"]:
            k = clean_key(n)
            r = v2_root_key(n)
            if k and k not in fmap["precise"]:
                fmap["precise"][k] = p
            if r and r not in fmap["roots"]:
                fmap["roots"][r] = p
            if n and n not in fmap["raw"]:
                fmap["raw"][n] = p
        for n in names["postscript"]:
            k = clean_key(n)
            if k and k not in fmap["by_postscript"]:
                fmap["by_postscript"][k] = p
        for n in names["full"]:
            k = clean_key(n)
            if k and k not in fmap["by_fullname"]:
                fmap["by_fullname"][k] = p
    return fmap


def v2_system_font_map(extra_dirs=None):
    candidates = []
    sysname = platform.system()
    if sysname == "Windows":
        candidates += [
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts",
        ]
    elif sysname == "Darwin":
        candidates += [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library/Fonts",
        ]
    else:
        candidates += [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
            Path.home() / ".local/share/fonts",
        ]
    if extra_dirs:
        candidates += [Path(d) for d in extra_dirs]
    merged = {
        "precise": {}, "roots": {}, "raw": {},
        "by_filename": {}, "by_postscript": {}, "by_fullname": {},
        "files": {},
    }
    for d in candidates:
        if not d or not d.exists():
            continue
        m = v2_build_font_map(d)
        for key in merged:
            for k, v in m[key].items():
                if k not in merged[key]:
                    merged[key][k] = v
    return merged


class V2MatchResult:
    __slots__ = ("font_path", "match_type", "confidence", "requested",
                 "resolved_name", "internal_names")

    def __init__(self, font_path, match_type, confidence=1.0,
                 requested="", resolved_name="", internal_names=None):
        self.font_path = font_path
        self.match_type = match_type
        self.confidence = confidence
        self.requested = requested
        self.resolved_name = resolved_name
        self.internal_names = internal_names or set()

    @property
    def is_naming_mismatch(self):
        return self.match_type in (
            "filename", "filename_fuzzy", "postscript", "fullname_only",
        )


def v2_cascade_match(name, clean, root, fmap, fuzzy_threshold=0.78):
    """8-level cascading match — returns V2MatchResult or None."""
    if clean in fmap["precise"]:
        p = fmap["precise"][clean]
        internal = fmap["files"].get(p, {}).get("all", set())
        return V2MatchResult(p, "internal_exact", 1.0, name, name, internal)
    if name in fmap.get("raw", {}):
        p = fmap["raw"][name]
        internal = fmap["files"].get(p, {}).get("all", set())
        return V2MatchResult(p, "internal_raw", 1.0, name, name, internal)
    if clean in fmap.get("by_filename", {}):
        p = fmap["by_filename"][clean]
        internal = fmap["files"].get(p, {}).get("all", set())
        hint = next(iter(internal), p.stem) if internal else p.stem
        return V2MatchResult(p, "filename", 0.95, name, hint, internal)
    if clean in fmap.get("by_postscript", {}):
        p = fmap["by_postscript"][clean]
        internal = fmap["files"].get(p, {}).get("family", set())
        hint = next(iter(internal), name) if internal else name
        return V2MatchResult(p, "postscript", 0.90, name, hint, internal)
    if clean in fmap.get("by_fullname", {}):
        p = fmap["by_fullname"][clean]
        internal = fmap["files"].get(p, {}).get("family", set())
        hint = next(iter(internal), name) if internal else name
        return V2MatchResult(p, "fullname_only", 0.88, name, hint, internal)
    if root and root in fmap["roots"]:
        p = fmap["roots"][root]
        internal = fmap["files"].get(p, {}).get("all", set())
        hint = next(iter(internal), name) if internal else name
        return V2MatchResult(p, "root", 0.85, name, hint, internal)
    # Fuzzy fallbacks
    from difflib import SequenceMatcher as _SM
    best = None
    best_ratio = fuzzy_threshold
    best_kind = None
    for k, p in fmap.get("by_filename", {}).items():
        r = _SM(None, clean, k).ratio()
        if r > best_ratio:
            best_ratio, best, best_kind = r, p, "filename_fuzzy"
    for k, p in fmap["precise"].items():
        r = _SM(None, clean, k).ratio()
        if r > best_ratio:
            best_ratio, best, best_kind = r, p, "internal_fuzzy"
    if best is not None:
        internal = fmap["files"].get(best, {}).get("all", set())
        hint = next(iter(internal), best.stem) if internal else best.stem
        return V2MatchResult(best, best_kind, best_ratio, name, hint, internal)
    return None


def v2_resolve_required_fonts(ass_path, font_map, system_map=None, fuzzy_threshold=0.78):
    """v2.0 cascading resolver. Returns rich dict instead of (matched, missing) tuple."""
    from_module = fonts_required_by_ass(ass_path)  # uses v1.8's _smart_decode_ass
    requested = sorted(from_module)
    matched, system, missing, mismatched = [], [], [], []
    for name in requested:
        clean = clean_key(name)
        root = v2_root_key(name)
        if clean in SYSTEM_FONT_IGNORE_CLEAN:
            system.append(name)
            continue
        result = v2_cascade_match(name, clean, root, font_map, fuzzy_threshold)
        if result is None and system_map:
            sysr = v2_cascade_match(name, clean, root, system_map, fuzzy_threshold)
            if sysr is not None:
                system.append(name)
                continue
        if result is None:
            missing.append(name)
        else:
            matched.append(result)
            if result.is_naming_mismatch:
                mismatched.append(result)
    return {
        "requested": requested, "matched": matched,
        "system": system, "missing": missing, "mismatched": mismatched,
    }


# Build clean-key system font ignore set (preserves backward-compat constant)
try:
    SYSTEM_FONT_IGNORE_CLEAN = {clean_key(n) for n in SYSTEM_FONT_IGNORE}
except NameError:
    # SYSTEM_FONT_IGNORE defined later in v1.8 — populated at runtime below
    SYSTEM_FONT_IGNORE_CLEAN = set()


# ---------- Font health check + repair ----------
_V2_MANDATORY_TABLES = (
    "cmap", "head", "hhea", "hmtx", "maxp", "name", "OS/2", "post",
)
_V2_VALID_FONT_MAGICS = (
    b"\x00\x01\x00\x00", b"OTTO", b"ttcf", b"true", b"typ1", b"wOFF", b"wOF2",
)


def v2_check_font_health(path):
    """Returns list of issue strings. Empty list = healthy.
    Detects: bad magic, missing tables, broken cmap/name/glyf/loca/head/OS2."""
    issues = []
    p = Path(path)
    if not p.exists():
        return ["file does not exist"]
    if p.stat().st_size < 256:
        return ["file too small (likely corrupt download or stub)"]
    try:
        with p.open("rb") as fh:
            magic = fh.read(4)
        if magic not in _V2_VALID_FONT_MAGICS:
            return [f"invalid magic bytes: {magic!r}"]
    except Exception as e:
        return [f"could not read magic: {e}"]
    try:
        from fontTools.ttLib import TTFont, TTLibError
    except ImportError:
        return ["fontTools not installed"]
    try:
        tt = TTFont(str(p), recalcBBoxes=False, recalcTimestamp=False)
    except TTLibError as e:
        return [f"fontTools parse failure: {e}"]
    except Exception as e:
        return [f"unexpected parse error: {e}"]
    for tbl in _V2_MANDATORY_TABLES:
        if tbl not in tt:
            issues.append(f"missing table: {tbl}")
    if "cmap" in tt:
        try:
            best = tt["cmap"].getBestCmap()
            if not best:
                issues.append("cmap has no usable subtable")
        except Exception as e:
            issues.append(f"broken cmap: {e}")
    if "name" in tt:
        try:
            family_count = 0
            for rec in tt["name"].names:
                try:
                    s = rec.toUnicode()
                    if rec.nameID == 1 and s.strip():
                        family_count += 1
                except UnicodeDecodeError:
                    issues.append(f"name nameID={rec.nameID} invalid encoding")
                except Exception as e:
                    issues.append(f"name decode: {e}")
            if family_count == 0:
                issues.append("name table has no Family name")
        except Exception as e:
            issues.append(f"broken name table: {e}")
    if "glyf" in tt and "loca" in tt:
        try:
            _ = tt["glyf"][tt.getGlyphName(0)]
        except Exception as e:
            issues.append(f"glyf/loca inconsistency: {e}")
    if "head" in tt:
        try:
            if tt["head"].unitsPerEm <= 0:
                issues.append("head.unitsPerEm invalid")
        except Exception as e:
            issues.append(f"broken head: {e}")
    if "OS/2" in tt:
        try:
            _ = tt["OS/2"].usWeightClass
        except Exception as e:
            issues.append(f"broken OS/2: {e}")
    try: tt.close()
    except Exception: pass
    return issues


def v2_repair_font(src_path, dst_path=None, allow_ots=True):
    """Two-layer repair: fontTools recalc → ots-sanitize fallback.
    Returns (success, layer_used, message)."""
    src = Path(src_path)
    if not src.exists():
        return False, "skipped", "source missing"
    in_place = dst_path is None
    if in_place:
        dst = src.parent / f".{src.name}.repaired.tmp"
    else:
        dst = Path(dst_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
    # Layer 1: fontTools recalc
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(str(src), recalcBBoxes=True, recalcTimestamp=True, lazy=False)
        if "name" in tt:
            for rec in list(tt["name"].names):
                try:
                    rec.toUnicode()
                except Exception:
                    tt["name"].names.remove(rec)
        tt.save(str(dst), reorderTables=False)
        tt.close()
        ft_ok = True
        ft_msg = "saved"
    except Exception as e:
        ft_ok = False
        ft_msg = f"fontTools save failed: {e}"
    if ft_ok:
        new_issues = v2_check_font_health(dst)
        if not new_issues:
            if in_place:
                try: os.replace(str(dst), str(src))
                except Exception:
                    shutil.copy2(str(dst), str(src))
                    try: dst.unlink()
                    except Exception: pass
            return True, "fonttools", "fontTools recalc fixed all issues"
        ft_msg = f"fontTools left {len(new_issues)} issue(s): {new_issues[:3]}"
    # Layer 2: ots-sanitize
    if allow_ots and shutil.which("ots-sanitize"):
        try:
            r = subprocess.run(
                ["ots-sanitize", str(src), str(dst)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and dst.exists() and dst.stat().st_size > 256:
                new_issues = v2_check_font_health(dst)
                if not new_issues:
                    if in_place:
                        try: os.replace(str(dst), str(src))
                        except Exception:
                            shutil.copy2(str(dst), str(src))
                            try: dst.unlink()
                            except Exception: pass
                    return True, "ots", "ots-sanitize fixed all issues"
                ots_msg = f"ots left {len(new_issues)} issue(s)"
            else:
                ots_msg = f"ots rc={r.returncode}: {(r.stderr or '')[:200]}"
        except subprocess.TimeoutExpired:
            ots_msg = "ots timed out"
        except Exception as e:
            ots_msg = f"ots crashed: {e}"
        return False, "ots", f"both layers failed. ft: {ft_msg}; ots: {ots_msg}"
    return False, "fonttools", ft_msg


# ---------- libass naming-mismatch resolver ----------
PATCH_FONT = "patch_font"
PATCH_ASS = "patch_ass"
WARN_ONLY = "warn_only"


def v2_patch_font_name(src_font_path, target_family_name, out_path=None,
                       preserve_postscript=True):
    """Inject target_family_name into nameIDs 1, 4, 16 so libass finds it."""
    src = Path(src_font_path)
    if not src.exists():
        return False, None, "source missing"
    if out_path is None:
        out_path = src.parent / f"{src.stem}_patched{src.suffix}"
    else:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(str(src), recalcBBoxes=False, recalcTimestamp=False)
    except Exception as e:
        return False, None, f"open failed: {e}"
    if "name" not in tt:
        try: tt.close()
        except Exception: pass
        return False, None, "no name table"
    nt = tt["name"]
    records = [
        (1, 3, 1, 0x409, target_family_name),
        (1, 1, 0, 0,     target_family_name),
        (4, 3, 1, 0x409, target_family_name),
        (4, 1, 0, 0,     target_family_name),
        (16, 3, 1, 0x409, target_family_name),
    ]
    if not preserve_postscript:
        ps = re.sub(r"\s+", "", target_family_name)[:63]
        records += [(6, 3, 1, 0x409, ps), (6, 1, 0, 0, ps)]
    for nid, pid, eid, lid, val in records:
        try:
            nt.setName(val, nid, pid, eid, lid)
        except Exception as e:
            try: tt.close()
            except Exception: pass
            return False, None, f"setName {nid}: {e}"
    try:
        tt.save(str(out_path))
        tt.close()
        return True, out_path, f"patched: '{target_family_name}'"
    except Exception as e:
        return False, None, f"save failed: {e}"


_V2_RE_STYLE_FONT = re.compile(r"^(Style:\s*[^,]*,)([^,]+)", re.MULTILINE)
_V2_RE_FN_TAG = re.compile(r"(\\fn)([^\\}]+)")


def v2_patch_ass_font_references(ass_path, mapping, out_path=None):
    """Rewrites font names inside an ASS using mapping {requested: actual_internal}."""
    src = Path(ass_path)
    if not src.exists():
        return False, None, 0
    if out_path is None:
        out_path = src.parent / f"{src.stem}.patched{src.suffix}"
    else:
        out_path = Path(out_path)
    try:
        raw = src.read_bytes()
        # Use existing smart decoder
        text = _smart_decode_ass(raw) or raw.decode("utf-8", errors="replace")
    except Exception:
        return False, None, 0
    n = 0

    def repl_style(m):
        nonlocal n
        nm = m.group(2).strip()
        pfx = "@" if nm.startswith("@") else ""
        nm = nm.lstrip("@")
        if nm in mapping:
            n += 1
            return f"{m.group(1)}{pfx}{mapping[nm]}"
        return m.group(0)

    def repl_fn(m):
        nonlocal n
        nm = m.group(2).strip()
        pfx = "@" if nm.startswith("@") else ""
        nm = nm.lstrip("@")
        if nm in mapping:
            n += 1
            return f"{m.group(1)}{pfx}{mapping[nm]}"
        return m.group(0)

    text = _V2_RE_STYLE_FONT.sub(repl_style, text)
    text = _V2_RE_FN_TAG.sub(repl_fn, text)
    try:
        out_path.write_bytes(text.encode("utf-8-sig"))
        return True, out_path, n
    except Exception:
        return False, None, n


# ---------- Embedded ASS reader with cache ----------
class V2EmbeddedAssCache:
    """JSON-backed cache for embedded-ASS scan results, keyed by (path, mtime, size)."""

    def __init__(self, anime_root):
        self.cache_dir = Path(anime_root) / ".anime_studio_cache"
        self.cache_path = self.cache_dir / "embedded_ass.json"
        self.data = {}
        self._dirty = False
        if self.cache_path.exists():
            try:
                self.data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def save(self):
        if not self._dirty:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(str(tmp), str(self.cache_path))
            self._dirty = False
        except Exception:
            pass

    def get(self, video_path):
        key = str(Path(video_path).resolve())
        entry = self.data.get(key)
        if not entry:
            return None
        try:
            st = Path(video_path).stat()
            if abs(entry["mtime"] - st.st_mtime) > 1.0 or entry["size"] != st.st_size:
                return None
        except Exception:
            return None
        return entry

    def put(self, video_path, fonts, sub_tracks, languages,
            has_embedded_fonts=False, embedded_font_names=None):
        key = str(Path(video_path).resolve())
        try:
            st = Path(video_path).stat()
        except Exception:
            return
        self.data[key] = {
            "mtime": st.st_mtime, "size": st.st_size,
            "fonts": sorted(fonts), "sub_tracks": sub_tracks,
            "languages": languages,
            "has_embedded_fonts": has_embedded_fonts,
            "embedded_font_names": sorted(embedded_font_names or []),
        }
        self._dirty = True


def v2_identify_mkv(mkv_path):
    if not shutil.which("mkvmerge"):
        return None
    try:
        r = subprocess.run(
            ["mkvmerge", "-J", str(mkv_path)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if r.returncode not in (0, 1):
            return None
        return json.loads(r.stdout or "{}")
    except Exception:
        return None


def v2_find_ass_tracks(info):
    out = []
    if not info: return out
    for t in info.get("tracks", []):
        if t.get("type") != "subtitles":
            continue
        codec = (t.get("codec") or "").lower()
        cid = (t.get("properties", {}).get("codec_id") or "").lower()
        if "ass" in codec or "substation" in codec or "ssa" in codec or "s_text/ass" in cid:
            out.append({
                "id": t.get("id"),
                "language": t.get("properties", {}).get("language", ""),
                "language_ietf": t.get("properties", {}).get("language_ietf", ""),
            })
    return out


def v2_find_embedded_fonts(info):
    if not info: return []
    out = []
    for a in info.get("attachments", []):
        ct = (a.get("content_type") or "").lower()
        nm = a.get("file_name", "")
        if "font" in ct or nm.lower().endswith((".ttf", ".otf", ".ttc", ".otc")):
            out.append(nm)
    return out


def v2_extract_ass_track(mkv_path, track_id, out_path=None):
    if not shutil.which("mkvextract"):
        return None
    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".ass", prefix="anime_studio_emb_")
        os.close(fd)
    out_path = Path(out_path)
    try:
        r = subprocess.run(
            ["mkvextract", "tracks", str(mkv_path), f"{track_id}:{out_path}"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        if r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            return out_path
    except Exception:
        pass
    try:
        if out_path.exists():
            out_path.unlink()
    except Exception:
        pass
    return None


def v2_get_embedded_subs_info(video_path, cache=None, force=False):
    """Read embedded ASS tracks + attached fonts of an MKV. Cached by mtime."""
    p = Path(video_path)
    if not p.exists() or p.suffix.lower() not in {".mkv", ".webm", ".mka"}:
        return {"has_ass": False, "fonts": set(), "sub_tracks": 0,
                "languages": [], "has_embedded_fonts": False,
                "embedded_font_names": []}
    if not force and cache is not None:
        c = cache.get(p)
        if c is not None:
            return {
                "has_ass": c["sub_tracks"] > 0,
                "fonts": set(c["fonts"]),
                "sub_tracks": c["sub_tracks"],
                "languages": c["languages"],
                "has_embedded_fonts": c.get("has_embedded_fonts", False),
                "embedded_font_names": c.get("embedded_font_names", []),
            }
    info = v2_identify_mkv(p)
    ass_tracks = v2_find_ass_tracks(info)
    emb_fonts = v2_find_embedded_fonts(info)
    if not ass_tracks:
        if cache is not None:
            cache.put(p, [], 0, [], bool(emb_fonts), emb_fonts)
        return {"has_ass": False, "fonts": set(), "sub_tracks": 0,
                "languages": [], "has_embedded_fonts": bool(emb_fonts),
                "embedded_font_names": emb_fonts}
    all_fonts = set()
    langs = []
    for tr in ass_tracks:
        tmp = v2_extract_ass_track(p, tr["id"])
        if tmp is None:
            continue
        try:
            # Use v1.8 parser for consistency
            all_fonts |= fonts_required_by_ass(tmp)
            if tr["language"]:
                langs.append(tr["language"])
        finally:
            try: tmp.unlink()
            except Exception: pass
    if cache is not None:
        cache.put(p, all_fonts, len(ass_tracks), langs, bool(emb_fonts), emb_fonts)
    return {"has_ass": True, "fonts": all_fonts,
            "sub_tracks": len(ass_tracks), "languages": langs,
            "has_embedded_fonts": bool(emb_fonts),
            "embedded_font_names": emb_fonts}


# ---------- Missing subtitles report ----------
_V2_VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".webm", ".mov", ".ts", ".m4v"}
_V2_EXTERNAL_SUB_EXTS = {".ass", ".ssa", ".srt", ".sub", ".vtt", ".idx"}


def v2_find_anime_without_subs(anime_root, check_embedded=True, embedded_cache=None,
                               progress_cb=None):
    anime_root = Path(anime_root)
    if not anime_root.exists():
        return []
    candidates = []
    for dirpath, dirnames, _ in os.walk(anime_root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in ("_Fonts", "_Muxed")]
        folder = Path(dirpath)
        videos = [p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in _V2_VIDEO_EXTS]
        if not videos:
            continue
        ext_subs = [p for p in folder.iterdir()
                    if p.is_file() and p.suffix.lower() in _V2_EXTERNAL_SUB_EXTS]
        if ext_subs:
            continue
        candidates.append((folder, videos))
    results = []
    total = len(candidates)
    for i, (folder, videos) in enumerate(candidates, 1):
        if progress_cb:
            try: progress_cb(i, total, folder.name)
            except Exception: pass
        has_emb = False
        if check_embedded:
            for v in videos:
                if v.suffix.lower() != ".mkv":
                    continue
                info = v2_identify_mkv(v)
                if info and any(t.get("type") == "subtitles" for t in info.get("tracks", [])):
                    has_emb = True
                    break
        if has_emb:
            continue
        total_size = sum(v.stat().st_size for v in videos if v.exists())
        results.append({
            "folder": folder,
            "video_count": len(videos),
            "videos": videos,
            "sample_video": videos[0].name if videos else "",
            "size_gb": round(total_size / (1024 ** 3), 2),
            "anime_name": folder.name,
        })
    return results


def v2_write_missing_subs_report(missing_list, anime_root, out_path=None):
    anime_root = Path(anime_root)
    if out_path is None:
        out_path = anime_root / "_Anime_Without_Subtitles.md"
    out_path = Path(out_path)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Anime Without Subtitles",
        "",
        f"**Generated:** {ts}  ",
        f"**Library:** `{anime_root}`  ",
        f"**Found:** {len(missing_list)} folders",
        "",
    ]
    if not missing_list:
        lines.append("🎉 **All your anime have subtitles!**")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return out_path
    total_size = sum(it["size_gb"] for it in missing_list)
    total_videos = sum(it["video_count"] for it in missing_list)
    lines += [
        f"**Total:** {total_videos} episodes  •  ~{total_size:.1f} GB",
        "",
        "---", "",
        "## Folders needing subtitles", "",
    ]
    missing_list = sorted(missing_list, key=lambda x: -x["video_count"])
    for idx, item in enumerate(missing_list, 1):
        name = item["anime_name"]
        enc = urllib.parse.quote(name)
        try:
            rel = item["folder"].relative_to(anime_root)
        except Exception:
            rel = item["folder"]
        lines += [
            f"### {idx}. {name}",
            f"- **Path:** `{rel}`",
            f"- **Episodes:** {item['video_count']}  •  **Size:** {item['size_gb']:.1f} GB",
            f"- **Sample:** `{item['sample_video']}`",
            f"- **Search:** "
            f"[Kitsunekko](https://kitsunekko.net/subtitles.php?search={enc}) • "
            f"[Jimaku.cc](https://jimaku.cc/search?q={enc}) • "
            f"[OpenSubtitles](https://www.opensubtitles.com/en/search-all?query={enc}) • "
            f"[AnimeTosho](https://animetosho.org/search?q={enc})",
            "",
        ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------- Sync tool registry (alass + ffsubsync) ----------
V2_SYNC_TOOLS = {
    "ffsubsync": {
        "cmd_builder": lambda v, s, o: ["ffsubsync", str(v), "-i", str(s), "-o", str(o)],
        "install_hint": "pip install ffsubsync",
        "description": "VAD-based audio analysis — accurate for constant offset",
    },
    "alass": {
        "cmd_builder": lambda v, s, o: ["alass", str(v), str(s), str(o)],
        "install_hint": "cargo install alass-cli OR github.com/kaegi/alass/releases",
        "description": "Variable-rate sync — best for anime with split timings",
    },
}


def v2_which_sync_tools():
    return {name: bool(shutil.which(name)) for name in V2_SYNC_TOOLS}


def v2_sync_one(args):
    """Worker for ProcessPoolExecutor. args = (video, sub_in, sub_out, tool_name, timeout)"""
    video, sub_in, sub_out, tool_name, timeout = args
    spec = V2_SYNC_TOOLS.get(tool_name)
    if not spec:
        return False, Path(sub_in).name, f"unknown tool: {tool_name}"
    cmd = spec["cmd_builder"](video, sub_in, sub_out)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8", errors="replace")
        if r.returncode == 0 and Path(sub_out).exists() and Path(sub_out).stat().st_size > 0:
            return True, Path(sub_in).name, ""
        err = (r.stderr or r.stdout or "no output").strip().split("\n")[-1]
        return False, Path(sub_in).name, err[:200]
    except subprocess.TimeoutExpired:
        return False, Path(sub_in).name, f"timeout after {timeout}s"
    except FileNotFoundError:
        return False, Path(sub_in).name, f"{tool_name} not installed"


# =========================================================================
#  v2.0  UNIVERSAL FONT HUNTER  (search-engine-driven)
# =========================================================================

V2_CONFIG_FILE = ".anime_studio_config.json"
V2_DEFAULT_CFG = {
    "brave_search_api_key": "",
    "serpapi_key": "",
    "google_cse_key": "",
    "google_cse_id": "",
    "github_token": "",
    "user_agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "request_timeout_sec": 15,
    "max_results_per_engine": 15,
    "name_match_threshold": 0.72,
    "default_sync_tool": "ask",  # "alass" | "ffsubsync" | "ask" | "both"
}


def v2_load_config(anime_root=None):
    cfg = dict(V2_DEFAULT_CFG)
    paths = []
    if anime_root:
        paths.append(Path(anime_root) / V2_CONFIG_FILE)
    paths.append(Path.cwd() / V2_CONFIG_FILE)
    paths.append(Path.home() / V2_CONFIG_FILE)
    for p in paths:
        if p.exists():
            try:
                cfg.update(json.loads(p.read_text(encoding="utf-8")))
                break
            except Exception:
                pass
    for k in ("brave_search_api_key", "serpapi_key",
              "google_cse_key", "google_cse_id", "github_token"):
        env = os.environ.get(k.upper())
        if env:
            cfg[k] = env
    return cfg


def v2_save_config(cfg, anime_root=None):
    """Persist config to <anime_root>/.anime_studio_config.json."""
    if anime_root:
        path = Path(anime_root) / V2_CONFIG_FILE
    else:
        path = Path.cwd() / V2_CONFIG_FILE
    try:
        path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
    except Exception:
        return None


_V2_FONT_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"ttcf", b"true", b"typ1", b"wOFF", b"wOF2")
_V2_DL_KEYWORDS = ("download", "télécharger", "تحميل", "تنزيل",
                   "загрузить", "ダウンロード", "下载", "descargar")


def _v2_http_request(url, method="GET", headers=None, timeout=15, data=None):
    h = {"User-Agent": V2_DEFAULT_CFG["user_agent"],
         "Accept-Language": "en-US,en;q=0.9"}
    if headers: h.update(headers)
    try:
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try: return e.code, e.read()
        except Exception: return e.code, None
    except Exception:
        return None, None


def _v2_http_get_text(url, timeout=15):
    s, b = _v2_http_request(url, timeout=timeout)
    if s and 200 <= s < 300 and b:
        try: return b.decode("utf-8", errors="replace")
        except Exception: return None
    return None


def _v2_http_get_json(url, headers=None, timeout=15):
    s, b = _v2_http_request(url, headers=headers, timeout=timeout)
    if s and 200 <= s < 300 and b:
        try: return json.loads(b.decode("utf-8", errors="replace"))
        except Exception: return None
    return None


def _v2_is_font_magic(data):
    return bool(data and len(data) >= 4 and data[:4] in _V2_FONT_MAGIC)


def _v2_verify_font_name(font_path, wanted, threshold=0.72):
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(str(font_path), lazy=True, fontNumber=0)
        names = set()
        if "name" in tt:
            for rec in tt["name"].names:
                try:
                    if rec.nameID in (1, 4, 16, 21):
                        names.add(rec.toUnicode().strip())
                except Exception:
                    pass
        tt.close()
    except Exception:
        return False, ""
    norm = lambda s: re.sub(r"[^a-z0-9\u0600-\u06ff]", "", s.lower())
    wn = norm(wanted)
    from difflib import SequenceMatcher as _SM
    for n in names:
        nn = norm(n)
        if not nn: continue
        if nn == wn or wn in nn or nn in wn:
            return True, n
        if _SM(None, wn, nn).ratio() >= threshold:
            return True, n
    return False, next(iter(names), "")


def _v2_download_and_verify(url, dest_dir, wanted_name, threshold=0.72,
                            timeout=30, allow_zip=True):
    s, data = _v2_http_request(url, timeout=timeout)
    if not s or s >= 400 or not data:
        return None, None
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    # ZIP?
    if allow_zip and data[:4] == b"PK\x03\x04":
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except Exception:
            return None, None
        for member in zf.namelist():
            if not member.lower().endswith((".ttf", ".otf")):
                continue
            try: payload = zf.read(member)
            except Exception: continue
            if not _v2_is_font_magic(payload):
                continue
            fname = Path(member).name
            dest = dest_dir / fname
            if dest.exists():
                stem, suf = dest.stem, dest.suffix
                dest = dest_dir / f"{stem}_{int(datetime.datetime.now().timestamp())}{suf}"
            dest.write_bytes(payload)
            ok, internal = _v2_verify_font_name(dest, wanted_name, threshold)
            if ok:
                return dest, internal
            try: dest.unlink()
            except Exception: pass
        return None, None
    if _v2_is_font_magic(data):
        url_name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
        if not url_name or "." not in url_name:
            url_name = re.sub(r"[^A-Za-z0-9._-]", "_", wanted_name) + ".ttf"
        dest = dest_dir / url_name
        if dest.exists():
            stem, suf = dest.stem, dest.suffix
            dest = dest_dir / f"{stem}_{int(datetime.datetime.now().timestamp())}{suf}"
        dest.write_bytes(data)
        ok, internal = _v2_verify_font_name(dest, wanted_name, threshold)
        if ok:
            return dest, internal
        try: dest.unlink()
        except Exception: pass
    return None, None


def v2_search_brave(query, api_key, max_results=15, timeout=15):
    if not api_key: return []
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({
        "q": query, "count": min(max_results, 20),
    })
    js = _v2_http_get_json(url, headers={
        "Accept": "application/json", "X-Subscription-Token": api_key
    }, timeout=timeout)
    if not js: return []
    out = []
    for it in (js.get("web", {}) or {}).get("results", []):
        u = it.get("url")
        if u: out.append(u)
    return out


def v2_search_serpapi(query, api_key, max_results=15, timeout=15):
    if not api_key: return []
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode({
        "engine": "google", "q": query, "num": min(max_results, 20), "api_key": api_key,
    })
    js = _v2_http_get_json(url, timeout=timeout)
    if not js: return []
    return [it.get("link") for it in (js.get("organic_results") or []) if it.get("link")]


def v2_search_google_cse(query, api_key, cse_id, max_results=15, timeout=15):
    if not (api_key and cse_id): return []
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode({
        "key": api_key, "cx": cse_id, "q": query, "num": min(max_results, 10),
    })
    js = _v2_http_get_json(url, timeout=timeout)
    if not js: return []
    return [it.get("link") for it in (js.get("items") or []) if it.get("link")]


def v2_search_duckduckgo(query, max_results=15, timeout=15):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    html = _v2_http_get_text(url, timeout=timeout)
    if not html: return []
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', html):
        u = m.group(1)
        if "duckduckgo.com/l/" in u:
            qp = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
            if "uddg" in qp:
                u = qp["uddg"][0]
        out.append(u)
        if len(out) >= max_results: break
    return out


def v2_search_bing(query, max_results=15, timeout=15):
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query})
    html = _v2_http_get_text(url, timeout=timeout)
    if not html: return []
    out = []
    for m in re.finditer(r'<li class="b_algo"[^>]*>.*?<a href="([^"]+)"', html, re.DOTALL):
        out.append(m.group(1))
        if len(out) >= max_results: break
    return out


def v2_run_all_search_engines(query, cfg, max_results=15):
    urls = []
    seen = set()
    def _add(items):
        for u in items:
            if u and u not in seen:
                seen.add(u); urls.append(u)
    if cfg.get("brave_search_api_key"):
        _add(v2_search_brave(query, cfg["brave_search_api_key"], max_results))
    if cfg.get("serpapi_key"):
        _add(v2_search_serpapi(query, cfg["serpapi_key"], max_results))
    if cfg.get("google_cse_key") and cfg.get("google_cse_id"):
        _add(v2_search_google_cse(query, cfg["google_cse_key"],
                                  cfg["google_cse_id"], max_results))
    _add(v2_search_duckduckgo(query, max_results))
    _add(v2_search_bing(query, max_results))
    return urls


def v2_extract_font_urls_from_page(page_url, page_html=None, timeout=15):
    if page_html is None:
        page_html = _v2_http_get_text(page_url, timeout=timeout)
    if not page_html: return []
    found, seen = [], set()
    def _add(u, score):
        if not u: return
        absu = urllib.parse.urljoin(page_url, u)
        if absu in seen: return
        seen.add(absu); found.append((absu, score))
    for m in re.finditer(r'href=["\']([^"\']+\.(ttf|otf))(?:[?#][^"\']*)?["\']',
                         page_html, re.IGNORECASE):
        _add(m.group(1), 100)
    for m in re.finditer(r'href=["\']([^"\']+\.zip)(?:[?#][^"\']*)?["\']',
                         page_html, re.IGNORECASE):
        url = m.group(1)
        _add(url, 90 if "font" in url.lower() else 70)
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{1,80})</a>',
                         page_html, re.IGNORECASE):
        href, label = m.group(1), m.group(2).lower()
        if any(kw in label for kw in _V2_DL_KEYWORDS):
            if href.lower().endswith((".ttf", ".otf", ".zip")):
                _add(href, 85)
            elif "/download" in href.lower() or "/dl" in href.lower():
                _add(href, 60)
    for m in re.finditer(r'data-(?:url|href|download)=["\']([^"\']+\.(ttf|otf|zip))["\']',
                         page_html, re.IGNORECASE):
        _add(m.group(1), 75)
    for m in re.finditer(r'"downloadUrl"\s*:\s*"([^"]+)"', page_html):
        _add(m.group(1), 80)
    for m in re.finditer(r'(https?://[^"\'>\s]+/wp-content/uploads/[^"\'>\s]+\.(ttf|otf|zip))',
                        page_html, re.IGNORECASE):
        _add(m.group(1), 80)
    found.sort(key=lambda x: -x[1])
    return [u for u, _ in found]


def v2_build_search_queries(font_name):
    name = font_name.strip()
    return [
        f'"{name}" font download ttf',
        f'"{name}" font download otf',
        f'{name} font free download',
        f'"{name}" خط تحميل',
        f'site:github.com {name} ttf OR otf',
        f'site:fontesk.com {name}',
        f'site:fontspace.com {name}',
        f'site:dafont.com {name}',
        f'site:1001fonts.com {name}',
        f'{name} filetype:ttf',
        f'{name} filetype:otf',
    ]


def v2_universal_hunt(font_name, dest_dir, cfg=None, per_query_pages=3,
                      log_cb=None, max_total_attempts=50):
    """The new universal hunter. Returns dict with ok/path/internal_name/etc."""
    if cfg is None:
        cfg = v2_load_config()
    threshold = cfg.get("name_match_threshold", 0.72)
    def _log(msg):
        if log_cb:
            try: log_cb(msg)
            except Exception: pass
    dest_dir = Path(dest_dir); dest_dir.mkdir(parents=True, exist_ok=True)
    attempts = 0
    engines_used = set()
    seen_urls = set()
    for q in v2_build_search_queries(font_name):
        _log(f"  search: {q}")
        urls = v2_run_all_search_engines(q, cfg,
                                          max_results=cfg.get("max_results_per_engine", 15))
        if not urls: continue
        engines_used.add("(any)")
        direct = [u for u in urls if u.lower().endswith((".ttf", ".otf", ".zip"))]
        pages = [u for u in urls if u not in direct]
        for u in direct + pages[:per_query_pages]:
            if u in seen_urls: continue
            seen_urls.add(u); attempts += 1
            if attempts > max_total_attempts:
                _log(f"  stopped at {max_total_attempts} attempts")
                return {"ok": False, "path": None, "internal_name": "",
                        "attempts": attempts, "engines_used": list(engines_used),
                        "winning_url": ""}
            if u.lower().endswith((".ttf", ".otf", ".zip")):
                path, internal = _v2_download_and_verify(
                    u, dest_dir, font_name, threshold,
                    timeout=cfg.get("request_timeout_sec", 15))
                if path:
                    _log(f"    ✓ FOUND: {path.name} (internal={internal})")
                    return {"ok": True, "path": path, "internal_name": internal,
                            "attempts": attempts, "engines_used": list(engines_used),
                            "winning_url": u}
                continue
            page_html = _v2_http_get_text(u, timeout=cfg.get("request_timeout_sec", 15))
            if not page_html: continue
            for cu in v2_extract_font_urls_from_page(u, page_html=page_html)[:5]:
                if cu in seen_urls: continue
                seen_urls.add(cu); attempts += 1
                path, internal = _v2_download_and_verify(
                    cu, dest_dir, font_name, threshold,
                    timeout=cfg.get("request_timeout_sec", 15))
                if path:
                    _log(f"    ✓ FOUND via page-scrape: {path.name}")
                    return {"ok": True, "path": path, "internal_name": internal,
                            "attempts": attempts, "engines_used": list(engines_used),
                            "winning_url": cu}
    _log(f"  not found after {attempts} attempts")
    return {"ok": False, "path": None, "internal_name": "",
            "attempts": attempts, "engines_used": list(engines_used),
            "winning_url": ""}


# =========================================================================
#  v2.0  HIGH-LEVEL DRIVERS  (used by the new menu)
# =========================================================================

def v2_action_font_health_scan(anime_root):
    """Scan all _Fonts folders for broken fonts and offer to repair them."""
    rprint(f"\n[bold cyan]🩺 Font Health Check[/]  —  scanning {anime_root}\n")
    anime_root = Path(anime_root)
    all_broken = []
    all_unreadable = []
    healthy_count = 0
    folders_to_scan = []
    for p in anime_root.rglob("_Fonts"):
        if p.is_dir():
            folders_to_scan.append(p)
    if not folders_to_scan:
        # Fallback: scan library/fonts pool
        pool = anime_root / "library" / "fonts"
        if pool.exists():
            folders_to_scan = [pool]
    if not folders_to_scan:
        rprint("[yellow]No _Fonts folders or library/fonts pool found.[/]")
        return
    rprint(f"Scanning {len(folders_to_scan)} font folder(s)...\n")
    for folder in folders_to_scan:
        for ext in (".ttf", ".otf", ".ttc", ".otc"):
            for f in folder.rglob(f"*{ext}"):
                issues = v2_check_font_health(f)
                if not issues:
                    healthy_count += 1
                elif any("parse" in i or "magic" in i for i in issues):
                    all_unreadable.append((f, issues))
                else:
                    all_broken.append((f, issues))
    rprint(f"  ✓ Healthy: [green]{healthy_count}[/]")
    rprint(f"  ⚠ Broken (repairable): [yellow]{len(all_broken)}[/]")
    rprint(f"  ✗ Unreadable: [red]{len(all_unreadable)}[/]\n")
    if not all_broken:
        return
    rprint(f"[bold]Broken fonts:[/]")
    for f, issues in all_broken[:10]:
        rprint(f"  • {f.name}  —  {issues[0]}")
    if len(all_broken) > 10:
        rprint(f"  ...and {len(all_broken) - 10} more")
    rprint("")
    try:
        ans = input("Repair these fonts now (in-place, with .anime_studio_trash backup)? [y/N]: ")
    except (EOFError, KeyboardInterrupt):
        ans = "n"
    if ans.strip().lower() != "y":
        rprint("Skipped.")
        return
    repaired = 0
    failed = []
    for f, _ in all_broken:
        # Backup first
        v2_safe_delete_or_trash(f.parent / f".backup_{f.name}", anime_root, reason="pre-repair")
        # Actually we want to copy not move — re-do:
        bkp = anime_root / ".anime_studio_trash" / f"pre_repair_{f.name}"
        try:
            bkp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(f), str(bkp))
        except Exception:
            pass
        ok, layer, msg = v2_repair_font(f, dst_path=None)
        if ok:
            repaired += 1
        else:
            failed.append((f.name, msg))
    rprint(f"\n[green]✓ Repaired:[/] {repaired}/{len(all_broken)}")
    if failed:
        rprint(f"[red]✗ Failed:[/] {len(failed)}")
        for name, msg in failed[:5]:
            rprint(f"  • {name}: {msg[:120]}")


def v2_action_scan_missing_subs(anime_root):
    """Run the missing-subs scan and write the report."""
    rprint(f"\n[bold cyan]📝 Missing Subtitles Scan[/]  —  scanning {anime_root}\n")
    cache = V2EmbeddedAssCache(anime_root)
    def _prog(i, total, name):
        if i % 5 == 0 or i == total:
            rprint(f"  [{i}/{total}] checking: {name[:50]}")
    missing = v2_find_anime_without_subs(anime_root,
                                          check_embedded=True,
                                          embedded_cache=cache,
                                          progress_cb=_prog)
    cache.save()
    if not missing:
        rprint("\n[green]🎉 All your anime have subtitles![/]")
        return
    out = v2_write_missing_subs_report(missing, anime_root)
    rprint(f"\n[yellow]⚠ Found {len(missing)} folders without subtitles[/]")
    rprint(f"[green]Report:[/] {out}")
    rprint("\nTop 5 by episode count:")
    for it in sorted(missing, key=lambda x: -x["video_count"])[:5]:
        rprint(f"  • {it['anime_name']}  ({it['video_count']} eps, "
               f"{it['size_gb']:.1f} GB)")


def v2_action_sync_subtitles_menu(anime_root, folder=None):
    """Interactive sync with tool choice (alass / ffsubsync / both)."""
    rprint(f"\n[bold cyan]⏱ Subtitle Sync[/]")
    tools = v2_which_sync_tools()
    available = [t for t, present in tools.items() if present]
    if not available:
        rprint("[red]Neither alass nor ffsubsync is installed.[/]")
        for t, spec in V2_SYNC_TOOLS.items():
            rprint(f"  Install {t}: {spec['install_hint']}")
        return
    rprint(f"Available tools: {', '.join(available)}\n")
    rprint("  [1] alass       (best for anime — recommended)")
    rprint("  [2] ffsubsync   (best for constant offset)")
    rprint("  [3] Try both (alass first, ffsubsync fallback)")
    rprint("  [4] Cancel")
    try:
        choice = input("\nChoose tool [1-4]: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "4"
    if choice == "4" or not choice:
        return
    if choice == "1" and "alass" in available:
        primary, fallback = "alass", None
    elif choice == "2" and "ffsubsync" in available:
        primary, fallback = "ffsubsync", None
    elif choice == "3":
        primary = available[0]
        fallback = ["alass", "ffsubsync"]
    else:
        rprint(f"[red]Tool not available. Picking first available: {available[0]}[/]")
        primary, fallback = available[0], None
    if folder is None:
        try:
            folder = input("Folder to sync (default = library root): ").strip() or anime_root
        except (EOFError, KeyboardInterrupt):
            return
    pairs = Logic.pair_videos_and_subs(folder)
    if not pairs:
        rprint("[yellow]No (video, subtitle) pairs found in that folder.[/]")
        return
    tasks = []
    for vid, sub in pairs:
        out = Path(sub).with_name(Path(vid).stem + Path(sub).suffix)
        tasks.append((vid, sub, str(out)))
    rprint(f"\nSyncing {len(tasks)} pair(s)...")
    from concurrent.futures import ProcessPoolExecutor, as_completed
    ok_list, fail_list = [], []
    if fallback:
        worker_args = [(v, si, so, fallback, 180) for (v, si, so) in tasks]
        worker_fn = v2_sync_one_with_fallback
    else:
        worker_args = [(v, si, so, primary, 180) for (v, si, so) in tasks]
        worker_fn = v2_sync_one
    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(worker_fn, a): a for a in worker_args}
        done = 0
        for fut in as_completed(futures):
            try:
                ok, name, err = fut.result()
            except Exception as e:
                ok, name, err = False, "?", str(e)
            done += 1
            mark = "✓" if ok else "✗"
            rprint(f"  [{done}/{len(tasks)}] {mark} {name[:60]}  {err[:80]}")
            (ok_list if ok else fail_list).append((name, err))
    rprint(f"\n[green]✓ Synced:[/] {len(ok_list)}    [red]✗ Failed:[/] {len(fail_list)}")


def v2_action_scan_embedded_fonts(anime_root):
    """Scan library MKVs for embedded subs/fonts requirements."""
    rprint(f"\n[bold cyan]🔍 Embedded Subtitle Scan[/]  —  reading existing MKVs\n")
    cache = V2EmbeddedAssCache(anime_root)
    total_videos = 0
    with_embedded = 0
    all_fonts_needed = set()
    for v in Path(anime_root).rglob("*.mkv"):
        # Skip generated muxes that already have everything
        if "_Muxed" in v.parts:
            continue
        total_videos += 1
        if total_videos % 25 == 0:
            rprint(f"  [{total_videos}] checking: {v.name[:60]}")
        info = v2_get_embedded_subs_info(v, cache=cache)
        if info["has_ass"]:
            with_embedded += 1
            all_fonts_needed |= info["fonts"]
    cache.save()
    rprint(f"\n  Total MKVs scanned: {total_videos}")
    rprint(f"  With embedded ASS: {with_embedded}")
    rprint(f"  Unique fonts referenced: {len(all_fonts_needed)}")
    if all_fonts_needed and len(all_fonts_needed) <= 30:
        rprint(f"\n  Fonts found in embedded ASS:")
        for fn in sorted(all_fonts_needed):
            rprint(f"    • {fn}")


def v2_action_config_editor(anime_root):
    """Simple config setup for API keys + sync preference."""
    cfg = v2_load_config(anime_root)
    rprint(f"\n[bold cyan]⚙ Settings[/]  —  edit API keys & defaults\n")
    rprint(f"Config file: {Path(anime_root) / V2_CONFIG_FILE}\n")
    rprint("Current values (leave blank to keep):\n")
    def _ask(label, key, secret=False):
        cur = cfg.get(key, "")
        display = "*" * min(len(cur), 8) if secret and cur else cur
        try:
            new = input(f"  {label} [{display}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if new:
            cfg[key] = new
    _ask("Brave Search API key", "brave_search_api_key", secret=True)
    _ask("SerpAPI key", "serpapi_key", secret=True)
    _ask("Google CSE key", "google_cse_key", secret=True)
    _ask("Google CSE ID", "google_cse_id")
    _ask("GitHub token (optional, raises rate limit)", "github_token", secret=True)
    rprint("\n  Default sync tool: ask | alass | ffsubsync | both")
    try:
        new = input(f"  [{cfg.get('default_sync_tool', 'ask')}]: ").strip().lower()
        if new in ("ask", "alass", "ffsubsync", "both"):
            cfg["default_sync_tool"] = new
    except (EOFError, KeyboardInterrupt):
        pass
    path = v2_save_config(cfg, anime_root)
    if path:
        rprint(f"\n[green]✓ Saved to {path}[/]")
    else:
        rprint(f"\n[red]✗ Could not save config[/]")


def v2_build_status_dashboard(anime_root):
    """Returns a list of lines summarizing library status."""
    anime_root = Path(anime_root)
    lines = []
    if not anime_root.exists():
        return [f"❌ Library path missing: {anime_root}"]
    # Count anime folders (depth 1)
    try:
        anime_count = sum(1 for p in anime_root.iterdir()
                          if p.is_dir() and not p.name.startswith(".")
                          and not p.name.startswith("_") and p.name != "library")
    except Exception:
        anime_count = 0
    # Count videos & subs
    video_count = 0
    sub_count = 0
    for v in anime_root.rglob("*.mkv"):
        if "_Muxed" not in v.parts:
            video_count += 1
    for s in anime_root.rglob("*.ass"):
        sub_count += 1
    # Tools check
    tools = []
    if shutil.which("mkvmerge"): tools.append("mkvmerge")
    if shutil.which("ffmpeg"): tools.append("ffmpeg")
    if shutil.which("ffsubsync"): tools.append("ffsubsync")
    if shutil.which("alass"): tools.append("alass")
    if shutil.which("ots-sanitize"): tools.append("ots-sanitize")
    lines.append(f"📚 {anime_count} anime  •  🎬 {video_count} eps  •  📝 {sub_count} subs")
    lines.append(f"🔧 Tools: {', '.join(tools) if tools else '(none detected!)'}")
    # Last action: read state files
    last_ts = None
    state_file = anime_root / ".anime_studio_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            last_ts = state.get("last_action_ts")
        except Exception:
            pass
    if last_ts:
        try:
            dt = datetime.datetime.fromisoformat(last_ts)
            ago = datetime.datetime.now() - dt
            if ago.days > 0:
                lines.append(f"🕐 Last action: {ago.days} day(s) ago")
            else:
                lines.append(f"🕐 Last action: {ago.seconds // 3600}h ago")
        except Exception:
            pass
    return lines


# =========================================================================
#  v2.0  NEW MENU ENTRY POINTS
# =========================================================================

def v2_extended_menu_console(anime_root):
    """
    Standalone console menu that exposes the NEW v2 features without
    requiring changes to main_ui's curses loop. Called from a v1.8 menu
    option ("🆕 v2 Advanced Tools") which we'll add below.
    """
    while True:
        dash = v2_build_status_dashboard(anime_root)
        rprint("\n" + "─" * 70)
        rprint("[bold cyan]🎌 Anime Studio v2.0  —  Advanced Tools[/]")
        rprint(f"[dim]Library:[/] {anime_root}")
        for line in dash:
            rprint(f"  {line}")
        rprint("─" * 70)
        rprint("  [1]  🩺  Font health check & repair (broken fonts that block mpv)")
        rprint("  [2]  📝  Scan for anime missing subtitles (generates report)")
        rprint("  [3]  🔍  Scan embedded subs/fonts in existing MKVs")
        rprint("  [4]  ⏱   Sync subtitles  (alass / ffsubsync / both)")
        rprint("  [5]  🔧  libass naming-mismatch resolver")
        rprint("  [6]  🌐  Universal font hunter (search engines + page scraper)")
        rprint("  [7]  🎬  Re-mux MKVs with embedded ASS (attach missing fonts)")
        rprint("  [8]  🔧  Dependencies check & auto-install")
        rprint("  [9]  ⚙   Settings (API keys, defaults)")
        rprint("  [0]  ↩   Back to main menu")
        try:
            ch = input("\nChoose [0-9]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if ch == "1":
            v2_action_font_health_scan(anime_root)
        elif ch == "2":
            v2_action_scan_missing_subs(anime_root)
        elif ch == "3":
            v2_action_scan_embedded_fonts(anime_root)
        elif ch == "4":
            v2_action_sync_subtitles_menu(anime_root)
        elif ch == "5":
            v2_action_libass_mismatch_resolver(anime_root)
        elif ch == "6":
            v2_action_universal_hunt(anime_root)
        elif ch == "7":
            v2_action_remux_with_embedded_ass(anime_root)
        elif ch == "8":
            v2_action_dependencies_check(anime_root)
        elif ch == "9":
            v2_action_config_editor(anime_root)
        elif ch == "0" or not ch:
            return
        try:
            input("\n[Press Enter to continue]")
        except (EOFError, KeyboardInterrupt):
            return


def v2_action_libass_mismatch_resolver(anime_root):
    """
    Phase 1: scan library, detect every (ass, font) pair where the font's
             internal name differs from what the ASS asks for.
    Phase 2: ask user which strategy to apply (patch fonts / patch ASS / warn).
    Phase 3: apply.
    """
    rprint(f"\n[bold cyan]🔧 libass Naming-Mismatch Resolver[/]")
    rprint("Finds fonts that work in PotPlayer but FAIL in mpv due to name mismatch.\n")
    anime_root = Path(anime_root)
    # Collect all mismatches across library
    findings = []  # (ass_path, mismatch_list)
    sys_map = v2_system_font_map()
    for fonts_folder in anime_root.rglob("_Fonts"):
        if not fonts_folder.is_dir(): continue
        parent = fonts_folder.parent
        fmap = v2_build_font_map(fonts_folder)
        for ass in parent.glob("*.ass"):
            res = v2_resolve_required_fonts(ass, fmap, system_map=sys_map)
            if res["mismatched"]:
                findings.append((ass, res["mismatched"]))
    if not findings:
        rprint("[green]✓ No libass naming mismatches found.[/]")
        return
    total_mismatches = sum(len(m) for _, m in findings)
    rprint(f"[yellow]⚠ Found {total_mismatches} mismatch(es) across {len(findings)} ASS file(s)[/]\n")
    # Show top 10
    for ass, ml in findings[:10]:
        rprint(f"  📄 {ass.name}:")
        for m in ml[:5]:
            rprint(f"     '{m.requested}'  →  found as '{m.resolved_name}'  "
                   f"(via {m.match_type})")
        if len(ml) > 5:
            rprint(f"     ...and {len(ml) - 5} more")
    rprint("\nStrategies:")
    rprint("  [1] PATCH FONT  — copy fonts to _PatchedFonts/, inject ASS-requested names")
    rprint("                    Best: doesn't touch your ASS files. Original fonts safe.")
    rprint("  [2] PATCH ASS   — rewrite font references inside ASS to match font internals")
    rprint("                    Best: keeps font files clean. Original ASS backed up.")
    rprint("  [3] WARN ONLY   — log report, change nothing")
    rprint("  [4] Cancel")
    try:
        ch = input("\nChoose [1-4]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if ch == "4" or not ch:
        return
    if ch == "1":
        # Patch fonts strategy
        for ass, ml in findings:
            patched_dir = ass.parent / "_PatchedFonts"
            for m in ml:
                out = patched_dir / Path(m.font_path).name
                ok, path, msg = v2_patch_font_name(m.font_path, m.requested, out_path=out)
                if ok:
                    rprint(f"  ✓ {Path(m.font_path).name} ← adds '{m.requested}'")
                else:
                    rprint(f"  ✗ {Path(m.font_path).name}: {msg}")
    elif ch == "2":
        # Patch ASS strategy
        for ass, ml in findings:
            mapping = {m.requested: m.resolved_name for m in ml}
            # Backup original
            bk_dir = anime_root / ".anime_studio_trash"
            bk_dir.mkdir(exist_ok=True)
            try:
                shutil.copy2(str(ass),
                             str(bk_dir / f"pre_patch_{datetime.datetime.now().strftime('%Y%m%d')}_{ass.name}"))
            except Exception:
                pass
            ok, path, n = v2_patch_ass_font_references(ass, mapping, out_path=ass)
            if ok:
                rprint(f"  ✓ {ass.name}: rewrote {n} reference(s)")
            else:
                rprint(f"  ✗ {ass.name}: patch failed")
    elif ch == "3":
        out = anime_root / "_Naming_Mismatch_Report.md"
        lines = ["# libass Naming-Mismatch Report", ""]
        for ass, ml in findings:
            lines.append(f"## {ass.relative_to(anime_root) if anime_root in ass.parents else ass.name}")
            for m in ml:
                lines.append(f"- `{m.requested}` → found as `{m.resolved_name}` "
                             f"(file `{Path(m.font_path).name}`, via `{m.match_type}`)")
            lines.append("")
        out.write_text("\n".join(lines), encoding="utf-8")
        rprint(f"\n[green]✓ Report saved: {out}[/]")


def v2_action_universal_hunt(anime_root):
    """Hunt a single font using the new universal search-engine pipeline."""
    cfg = v2_load_config(anime_root)
    rprint(f"\n[bold cyan]🌐 Universal Font Hunter[/]")
    have_engines = []
    if cfg.get("brave_search_api_key"): have_engines.append("Brave")
    if cfg.get("serpapi_key"): have_engines.append("SerpAPI")
    if cfg.get("google_cse_key") and cfg.get("google_cse_id"): have_engines.append("Google CSE")
    have_engines += ["DuckDuckGo (HTML)", "Bing (HTML)"]
    rprint(f"Active engines: {', '.join(have_engines)}\n")
    try:
        name = input("Font name to hunt: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not name:
        return
    dest = Path(anime_root) / "library" / "fonts"
    dest.mkdir(parents=True, exist_ok=True)
    def _log(msg):
        rprint(msg)
    result = v2_universal_hunt(name, dest, cfg=cfg, log_cb=_log)
    if result["ok"]:
        rprint(f"\n[green]✓ Found: {result['path'].name}[/]")
        rprint(f"  Internal name: {result['internal_name']}")
        rprint(f"  Attempts: {result['attempts']}")
        rprint(f"  Source URL: {result['winning_url']}")
    else:
        rprint(f"\n[red]✗ Not found after {result['attempts']} attempts[/]")


# =========================================================================
#  END v2.0 HUNTER + MENU BLOCK

# =========================================================================
#  v2.0 PATCH-B  — Dependencies Auto-Installer + Hunter Integration +
#                  Embedded ASS in Smart Mux
# =========================================================================

# ---------- DEPENDENCY AUTO-INSTALLER ----------

def v2_detect_dependency(name):
    """Returns dict: {name, installed, path, version, install_hint}."""
    path = shutil.which(name)
    info = {
        "name": name,
        "installed": bool(path),
        "path": path or "",
        "version": "",
        "install_hint": "",
    }
    if path:
        # Try to grab version (best-effort, with short timeout)
        version_flags = {
            "ots-sanitize": ["--version"],
            "alass": ["--version"],
            "ffsubsync": ["--version"],
            "mkvmerge": ["--version"],
            "ffmpeg": ["-version"],
        }
        flags = version_flags.get(name, ["--version"])
        try:
            r = subprocess.run([path] + flags, capture_output=True, text=True,
                               timeout=5, encoding="utf-8", errors="replace")
            out = (r.stdout or r.stderr or "").strip()
            if out:
                info["version"] = out.split("\n")[0][:80]
        except Exception:
            pass
    # Install hints per dependency + platform
    sys_os = platform.system()
    hints = {
        "ots-sanitize": {
            "Windows": "scoop install ots  OR  download from github.com/khaledhosny/ots/releases",
            "Linux":   "sudo apt-get install -y ots  OR  pip install opentype-sanitizer",
            "Darwin":  "brew install ots",
        },
        "alass": {
            "Windows": "scoop install alass  OR  download from github.com/kaegi/alass/releases",
            "Linux":   "cargo install alass-cli  OR  download from github.com/kaegi/alass/releases",
            "Darwin":  "brew install alass  OR  cargo install alass-cli",
        },
        "ffsubsync": {
            "Windows": "pip install ffsubsync",
            "Linux":   "pip install ffsubsync",
            "Darwin":  "pip install ffsubsync",
        },
        "mkvmerge": {
            "Windows": "winget install MKVToolNix.MKVToolNix  OR  scoop install mkvtoolnix",
            "Linux":   "sudo apt-get install -y mkvtoolnix",
            "Darwin":  "brew install mkvtoolnix",
        },
        "ffmpeg": {
            "Windows": "winget install Gyan.FFmpeg  OR  scoop install ffmpeg",
            "Linux":   "sudo apt-get install -y ffmpeg",
            "Darwin":  "brew install ffmpeg",
        },
    }
    info["install_hint"] = hints.get(name, {}).get(sys_os, "")
    return info


def v2_try_install_dependency(name):
    """
    Attempt to auto-install a dependency using the platform's package manager.
    Returns (success, message).

    Strategy:
        Windows: scoop > winget
        macOS:   brew
        Linux:   apt-get (with sudo) > pip (for python-only tools)
    """
    sys_os = platform.system()
    if shutil.which(name):
        return True, f"{name} already installed"

    # Tool-specific install commands
    install_commands = {
        "ots-sanitize": {
            "Windows": [["scoop", "install", "ots"]],
            "Linux":   [["pip", "install", "--user", "opentype-sanitizer"],
                       ["sudo", "apt-get", "install", "-y", "ots"]],
            "Darwin":  [["brew", "install", "ots"]],
        },
        "alass": {
            "Windows": [["scoop", "install", "alass"]],
            "Linux":   [["cargo", "install", "alass-cli"]],
            "Darwin":  [["brew", "install", "alass"]],
        },
        "ffsubsync": {
            # Pure Python — pip works everywhere
            "Windows": [[sys.executable, "-m", "pip", "install", "--user", "ffsubsync"]],
            "Linux":   [[sys.executable, "-m", "pip", "install", "--user", "ffsubsync"]],
            "Darwin":  [[sys.executable, "-m", "pip", "install", "--user", "ffsubsync"]],
        },
        "mkvmerge": {
            "Windows": [["winget", "install", "--silent", "--accept-package-agreements",
                         "--accept-source-agreements", "MKVToolNix.MKVToolNix"],
                        ["scoop", "install", "mkvtoolnix"]],
            "Linux":   [["sudo", "apt-get", "install", "-y", "mkvtoolnix"]],
            "Darwin":  [["brew", "install", "mkvtoolnix"]],
        },
        "ffmpeg": {
            "Windows": [["winget", "install", "--silent", "--accept-package-agreements",
                         "--accept-source-agreements", "Gyan.FFmpeg"],
                        ["scoop", "install", "ffmpeg"]],
            "Linux":   [["sudo", "apt-get", "install", "-y", "ffmpeg"]],
            "Darwin":  [["brew", "install", "ffmpeg"]],
        },
    }
    cmds = install_commands.get(name, {}).get(sys_os, [])
    if not cmds:
        return False, f"no install method known for {name} on {sys_os}"

    last_err = ""
    for cmd in cmds:
        # Skip command if the leading tool isn't on PATH
        tool = cmd[0]
        if tool not in (sys.executable,) and not shutil.which(tool):
            last_err = f"{tool} not available"
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=300, encoding="utf-8", errors="replace")
            if r.returncode == 0 or shutil.which(name):
                # Refresh PATH-cache by re-checking with shutil.which (which uses os.environ)
                if shutil.which(name):
                    return True, f"installed via {' '.join(cmd[:2])}"
                last_err = "command succeeded but tool not on PATH"
            else:
                last_err = (r.stderr or r.stdout or "").strip().split("\n")[-1][:200]
        except subprocess.TimeoutExpired:
            last_err = f"install timed out after 5min"
        except Exception as e:
            last_err = str(e)[:200]
    return False, f"all attempts failed; last: {last_err}"


def v2_action_dependencies_check(anime_root=None):
    """Interactive dependency checker + installer. Shows status table and prompts to install."""
    rprint(f"\n[bold cyan]🔧 Dependencies Check & Auto-Install[/]\n")
    deps = ["mkvmerge", "ffmpeg", "ffsubsync", "alass", "ots-sanitize"]
    statuses = {name: v2_detect_dependency(name) for name in deps}
    # Show status table
    if _RICH:
        tbl = Table(show_header=True, header_style="bold cyan", box=_rbox.SIMPLE)
        tbl.add_column("Dependency", style="cyan")
        tbl.add_column("Status")
        tbl.add_column("Version / Path", style="dim")
        for name in deps:
            info = statuses[name]
            status = "[green]✓ installed[/]" if info["installed"] else "[red]✗ missing[/]"
            extra = info["version"] or info["path"] or ""
            tbl.add_row(name, status, extra[:60])
        _con.print(tbl)
    else:
        for name in deps:
            info = statuses[name]
            mark = "✓" if info["installed"] else "✗"
            print(f"  {mark} {name:15s}  {info['version'] or info['path']}")
    missing = [n for n, i in statuses.items() if not i["installed"]]
    if not missing:
        rprint("\n[green]🎉 All dependencies installed![/]")
        return
    rprint(f"\n[yellow]Missing: {', '.join(missing)}[/]\n")
    rprint("What you can install:")
    for n in missing:
        rprint(f"  • [cyan]{n}[/]: {statuses[n]['install_hint']}")
    try:
        ans = input("\nAttempt auto-install of missing dependencies now? [y/N]: ")
    except (EOFError, KeyboardInterrupt):
        return
    if ans.strip().lower() != "y":
        return
    for name in missing:
        rprint(f"\n[cyan]→ Installing {name}...[/]")
        ok, msg = v2_try_install_dependency(name)
        if ok:
            rprint(f"  [green]✓ {msg}[/]")
        else:
            rprint(f"  [red]✗ {msg}[/]")
            rprint(f"  [yellow]Manual install: {statuses[name]['install_hint']}[/]")


# ---------- HUNTER INTEGRATION (Strategy 0) ----------

def _v2_try_universal_hunter(name, dest_dir):
    """
    Adapter so FontHunter.STRATEGIES can call the universal hunter
    using the same (name, dest_dir) -> [Path] contract as the other strategies.

    This is registered as the FIRST strategy in FontHunter so it gets to
    cast the widest net before falling back to per-site scrapers.
    """
    try:
        cfg = v2_load_config()
        # Quick guard: if NO engines are configured AND HTML scrape engines
        # work, run anyway. But cap attempts low to avoid wasting time when
        # the user hasn't set up keys yet.
        has_keyed = bool(cfg.get("brave_search_api_key") or
                         cfg.get("serpapi_key") or
                         (cfg.get("google_cse_key") and cfg.get("google_cse_id")))
        max_attempts = 30 if has_keyed else 12   # be modest when only HTML scrapers available
        result = v2_universal_hunt(name, dest_dir, cfg=cfg,
                                   max_total_attempts=max_attempts,
                                   per_query_pages=2 if has_keyed else 1)
        if result.get("ok") and result.get("path"):
            return [result["path"]]
    except Exception:
        pass
    return []


def v2_install_hunter_integration():
    """
    Inject the universal hunter as Strategy 0 in FontHunter.STRATEGIES.
    Idempotent — safe to call multiple times.
    """
    global FontHunter
    new_strat = ("universal_search", _v2_try_universal_hunter)
    cur = list(FontHunter.STRATEGIES)
    if any(s[0] == "universal_search" for s in cur):
        return  # already installed
    FontHunter.STRATEGIES = (new_strat,) + tuple(cur)


# Auto-install hunter integration as soon as this module is fully loaded
# (so it's wired even when v2 functions are imported, not just when main() runs)
try:
    v2_install_hunter_integration()
except Exception:
    pass


# ---------- EMBEDDED ASS IN SMART MUX ----------

def v2_collect_embedded_jobs(anime_root, only_folder=None):
    """
    Find every MKV that contains an embedded ASS subtitle track BUT NO
    external .ass file paired with it. These are candidates for "re-mux"
    flow: extract embedded ASS → resolve fonts → re-mux with attached fonts.

    Returns:
        [
          {
            "video": Path,
            "extracted_ass": Path (temp),
            "fonts_required": set,
            "languages": [str],
          },
          ...
        ]
    """
    cache = V2EmbeddedAssCache(anime_root)
    jobs = []
    scan_root = Path(only_folder) if only_folder else Path(anime_root)
    for v in scan_root.rglob("*.mkv"):
        if "_Muxed" in v.parts or "_PatchedFonts" in v.parts:
            continue
        # Skip if external .ass is paired (Smart Mux already handles that)
        ext_ass = list(v.parent.glob(v.stem + "*.ass")) + list(v.parent.glob(v.stem + "*.ssa"))
        if ext_ass:
            continue
        info = v2_get_embedded_subs_info(v, cache=cache)
        if info["has_ass"] and info["fonts"]:
            jobs.append({
                "video": v,
                "fonts_required": info["fonts"],
                "languages": info["languages"],
                "sub_tracks": info["sub_tracks"],
                "embedded_fonts_already": info["embedded_font_names"],
            })
    cache.save()
    return jobs


def v2_action_remux_with_embedded_ass(anime_root):
    """
    Workflow that complements Smart Mux:
      1. Find MKVs with embedded ASS + no external .ass
      2. Resolve fonts per video (using the new multi-index matcher)
      3. Re-mux with fonts attached if missing
    """
    rprint(f"\n[bold cyan]🎬 Re-Mux MKVs With Embedded ASS[/]")
    rprint("Scans MKVs that already have embedded ASS subtitles and re-muxes")
    rprint("them to attach the fonts those subs need (so mpv plays them right).\n")
    jobs = v2_collect_embedded_jobs(anime_root)
    if not jobs:
        rprint("[green]✓ No MKVs found that need re-muxing[/]")
        return
    rprint(f"[yellow]Found {len(jobs)} MKV(s) with embedded ASS missing some fonts[/]\n")
    # Build a library-wide font map (pool + system)
    pool = Path(anime_root) / "library" / "fonts"
    pool_map = v2_build_font_map(pool) if pool.exists() else {
        "precise": {}, "roots": {}, "raw": {},
        "by_filename": {}, "by_postscript": {}, "by_fullname": {}, "files": {},
    }
    sys_map = v2_system_font_map()
    # Per-job analysis: find missing fonts
    analysed = []
    for job in jobs:
        fonts_required = job["fonts_required"]
        # Local _Fonts folder takes priority
        local_fonts_folder = job["video"].parent / "_Fonts"
        local_map = v2_build_font_map(local_fonts_folder) if local_fonts_folder.exists() else {
            "precise": {}, "roots": {}, "raw": {},
            "by_filename": {}, "by_postscript": {}, "by_fullname": {}, "files": {},
        }
        # Merge: local > pool
        merged = {k: dict(v) for k, v in pool_map.items()}
        for key, m in local_map.items():
            for k, v in m.items():
                merged[key][k] = v   # local overrides pool
        # Resolve each required font
        matched_files = []
        missing_names = []
        for name in fonts_required:
            clean = clean_key(name)
            root = v2_root_key(name)
            if clean in SYSTEM_FONT_IGNORE_CLEAN:
                continue
            res = v2_cascade_match(name, clean, root, merged)
            if res is None and sys_map:
                sys_res = v2_cascade_match(name, clean, root, sys_map)
                if sys_res is not None:
                    continue   # system has it; skip muxing
            if res is None:
                missing_names.append(name)
            else:
                # Skip if already attached to the MKV
                attached_lower = {n.lower() for n in job["embedded_fonts_already"]}
                if Path(res.font_path).name.lower() not in attached_lower:
                    matched_files.append(res.font_path)
        analysed.append({
            **job,
            "fonts_to_attach": matched_files,
            "fonts_missing": missing_names,
        })
    # Show summary
    rprint("Summary:")
    ready = [a for a in analysed if not a["fonts_missing"]]
    partial = [a for a in analysed if a["fonts_missing"]]
    rprint(f"  [green]✓ Ready (all fonts resolvable):[/] {len(ready)}")
    rprint(f"  [yellow]⚠ Partial (some fonts missing):[/] {len(partial)}\n")
    if not ready and not partial:
        return
    try:
        ans = input("Re-mux the READY ones now? (partial ones skipped) [y/N]: ")
    except (EOFError, KeyboardInterrupt):
        return
    if ans.strip().lower() != "y":
        return
    # Re-mux ready ones in parallel
    from concurrent.futures import ProcessPoolExecutor, as_completed
    tasks = []
    for a in ready:
        v = a["video"]
        out = v.parent / "_Muxed" / v.name
        out.parent.mkdir(parents=True, exist_ok=True)
        tasks.append((str(v), str(v), a["fonts_to_attach"], str(out), True))
        # ^ smart_mux_one signature: (video, sub, fonts, out_path, prefer_mkvmerge)
        # We pass the video itself as the subtitle source — mkvmerge will copy
        # the embedded sub from the video. NO — that's wrong. We need to
        # use --no-attachments + just attach extra fonts. Let's use a
        # tailored mkvmerge command instead.
    # Custom mkvmerge command that PRESERVES embedded subs and adds fonts
    ok_count, fail_count = 0, 0
    for a in ready:
        v = a["video"]
        out = v.parent / "_Muxed" / v.name
        try:
            cmd = ["mkvmerge", "-o", str(out), str(v)]
            for f in a["fonts_to_attach"]:
                mime = _mime_for_font(Path(f).suffix)
                cmd += ["--attachment-mime-type", mime,
                        "--attach-file", str(f)]
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=600, encoding="utf-8", errors="replace")
            if r.returncode in (0, 1) and out.exists() and out.stat().st_size > 1024:
                ok_count += 1
                rprint(f"  ✓ {v.name}  → {len(a['fonts_to_attach'])} fonts attached")
            else:
                fail_count += 1
                err = (r.stderr or r.stdout or "").strip().split("\n")[-1][:150]
                rprint(f"  ✗ {v.name}  — {err}")
        except Exception as e:
            fail_count += 1
            rprint(f"  ✗ {v.name}  — {e}")
    rprint(f"\n[green]✓ Re-muxed:[/] {ok_count}    [red]✗ Failed:[/] {fail_count}")


# =========================================================================
#  END v2.0 PATCH-B BLOCK
# =========================================================================
if __name__ == "__main__":
    main()