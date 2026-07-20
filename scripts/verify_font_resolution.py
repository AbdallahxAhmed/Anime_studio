#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E Font Resolution Diagnostic Script for Anime Studio v3."""

import asyncio
import argparse
import re
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from src.config import AppConfig
from src.adapters.dependency_checker import DependencyChecker
from src.hunters.registry import HunterRegistry
from src.hunters.sources.mkv_extract import MkvExtractHunter
from src.hunters.sources.sibling_font import SiblingFontHunter
from src.hunters.system_font_hunter import SystemFontHunter
from src.hunters.sources.google_fonts import GoogleFontsHunter
from src.hunters.sources.fontsquirrel import FontSquirrelHunter
from src.hunters.sources.dafont import DaFontHunter
from src.hunters.sources.fontspace import FontSpaceHunter
from src.hunters.sources.befonts import BeFontsHunter
from src.hunters.sources.arabic_fonts import ArabicFontsHunter
from src.hunters.sources.search_engine import SearchEngineHunter
from src.core.font_cache import FontCache
from src.core.font_resolver import FontResolver
from src.models.font import FontQuery, FontAsset
from src.adapters.subprocess import SubprocessAdapter


def normalize_font_name(raw_name: str) -> str:
    """Normalize font name by stripping vertical prefix and weight suffixes."""
    name = raw_name.strip()
    if name.startswith("@"):
        name = name[1:].strip()

    suffixes = [
        "Bold",
        "Italic",
        "Light",
        "Regular",
        "SemiBold",
        "ExtraBold",
        "Medium",
        "Thin",
        "Black",
        "Heavy",
    ]

    changed = True
    while changed:
        changed = False
        for suff in suffixes:
            pattern = re.compile(rf"\b{suff}\b", re.IGNORECASE)
            match = pattern.search(name)
            if match and name[match.end() :].strip() == "":
                name = name[: match.start()].strip()
                changed = True
                break
    return name


def parse_fonts_from_ass(subtitle_path: Path) -> list[str]:
    """Parse unique font names from ASS subtitle file."""
    fonts: set[str] = set()
    try:
        content = subtitle_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"Error reading subtitle file: {e}")
        sys.exit(1)

    for line in content.splitlines():
        stripped = line.strip()
        # Parse Style: lines
        if stripped.startswith("Style:"):
            parts = stripped[6:].split(",")
            if len(parts) > 1:
                font_name = parts[1].strip()
                norm = normalize_font_name(font_name)
                if norm:
                    fonts.add(norm)

        # Parse \fn override tags
        matches = re.findall(r"\{[^}]*\\fn([^\\}]+)", stripped)
        for m in matches:
            font_name = m.strip()
            norm = normalize_font_name(font_name)
            if norm:
                fonts.add(norm)

    return sorted(list(fonts))


def get_font_mime_type(suffix: str) -> str:
    """Determine MIME type for a font based on its file extension."""
    ext = suffix.lower()
    if ext == ".otf":
        return "font/otf"
    elif ext == ".ttf":
        return "font/ttf"
    elif ext == ".ttc":
        return "font/collection"
    return "application/octet-stream"


def parse_mkvinfo_attachments(mkvinfo_stdout: str) -> list[dict[str, str]]:
    """Parse mkvinfo output and extract font attachments."""
    attachments: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in mkvinfo_stdout.splitlines():
        line_stripped = line.strip()
        if "Attached" in line_stripped or "Attachment" in line_stripped:
            if current and "name" in current:
                attachments.append(current)
            current = {}
        elif (
            "File name" in line_stripped
            or "file_name" in line_stripped
            or "Name:" in line_stripped
        ):
            parts = line_stripped.split(":", 1)
            if len(parts) > 1:
                current["name"] = parts[1].strip()
        elif (
            "Mime type" in line_stripped
            or "mime_type" in line_stripped
            or "MIME type:" in line_stripped
        ):
            parts = line_stripped.split(":", 1)
            if len(parts) > 1:
                current["mime"] = parts[1].strip()
        elif (
            "File data, size" in line_stripped
            or "size" in line_stripped
            or "Size:" in line_stripped
        ):
            parts = line_stripped.split(":", 1)
            if len(parts) > 1:
                size_str = parts[1].strip()
                digits = "".join(c for c in size_str if c.isdigit())
                if digits:
                    size_bytes = int(digits)
                    if size_bytes >= 1024 * 1024:
                        current["size"] = f"{size_bytes / (1024 * 1024):.1f} MB"
                    elif size_bytes >= 1024:
                        current["size"] = f"{size_bytes / 1024:.0f} KB"
                    else:
                        current["size"] = f"{size_bytes} B"
    if current and "name" in current:
        attachments.append(current)
    return attachments


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="E2E Font Resolution Diagnostic Script"
    )
    parser.add_argument("--episode", type=str, required=True, help="Path to source MKV")
    parser.add_argument(
        "--subtitle", type=str, required=True, help="Path to ASS subtitle file"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Skip actual mkvmerge call"
    )
    args = parser.parse_args()

    episode_path = Path(args.episode)
    subtitle_path = Path(args.subtitle)

    if not episode_path.is_file():
        print(f"Error: Episode file not found at {episode_path}")
        sys.exit(1)
    if not subtitle_path.is_file():
        print(f"Error: Subtitle file not found at {subtitle_path}")
        sys.exit(1)

    print("════════════════════════════════════════")
    print("STEP 1: Parsing fonts from ASS subtitle")
    print("════════════════════════════════════════")
    fonts_in_sub = parse_fonts_from_ass(subtitle_path)
    print(f"Found {len(fonts_in_sub)} unique fonts in subtitle: {fonts_in_sub}\n")

    print("════════════════════════════════════════")
    print("STEP 2: Resolving fonts through hunter chain")
    print("════════════════════════════════════════")

    # Manually bootstrap core services and hunters
    config = AppConfig.load_from_toml()
    cache_dir = config.font_cache_path
    if not cache_dir:
        d_path = Path("D:/Entertainment/.anime_studio/font_cache")
        if d_path.exists():
            cache_dir = d_path
        else:
            if sys.platform == "win32":
                cache_dir = Path("D:/Entertainment/.anime_studio/font_cache")
            else:
                cache_dir = Path.home() / ".anime_studio" / "font_cache"
    font_cache = FontCache(cache_dir=cache_dir)

    dependency_checker = DependencyChecker()
    tool_registry = dependency_checker.discover_all()
    subprocess_adapter = SubprocessAdapter(tool_registry=tool_registry)

    # Manually compose registry in same order as bootstrap.py
    hunter_registry = HunterRegistry(cooldown_s=config.circuit_breaker_cooldown_s)

    # Layer 1: MkvExtractHunter
    hunter_registry.register(
        MkvExtractHunter(
            subprocess_port=subprocess_adapter,
            library_path=config.library_path or episode_path.parent,
        )
    )
    # Layer 2: SiblingFontHunter
    hunter_registry.register(SiblingFontHunter())
    # Layer 3: SystemFontHunter
    hunter_registry.register(SystemFontHunter())
    # Layer 4: Online Hunters
    hunter_registry.register(GoogleFontsHunter(proxy=config.proxy))
    hunter_registry.register(FontSquirrelHunter(proxy=config.proxy))
    hunter_registry.register(DaFontHunter(proxy=config.proxy))
    hunter_registry.register(FontSpaceHunter(proxy=config.proxy))
    hunter_registry.register(BeFontsHunter(proxy=config.proxy))
    hunter_registry.register(ArabicFontsHunter(proxy=config.proxy))
    # Layer 5: SearchEngineHunter
    hunter_registry.register(SearchEngineHunter(proxy=config.proxy))

    font_resolver = FontResolver(
        registry=hunter_registry,
        cache=font_cache,
        config=config,
    )

    anime_title = episode_path.parent.name or "Unknown Anime"
    resolved_assets: list[FontAsset] = []
    missing_fonts: list[str] = []

    stats_cache = 0
    stats_mkv = 0
    stats_sibling = 0
    stats_system = 0
    stats_network = 0
    stats_search = 0

    non_cache_layer_used: str | None = None
    network_layer_used: str | None = None

    for f in fonts_in_sub:
        query = FontQuery(
            requested_name=f, anime_title=anime_title, episode_path=episode_path
        )
        try:
            asset = await font_resolver.resolve(query)
            resolved_assets.append(asset)

            # Identify which layer resolved it
            status_layer = f"L{asset.layer_found}"
            source_mapping = {
                "mkv_extract": "MkvExtractHunter",
                "sibling": "SiblingFontHunter",
                "system": "SystemFontHunter",
            }
            hunter_name = source_mapping.get(asset.source, asset.source)

            if asset.cache_hit:
                status_layer = "L0"
                hunter_name = "LocalCache"
                stats_cache += 1
            else:
                if asset.layer_found == 1:
                    stats_mkv += 1
                elif asset.layer_found == 2:
                    stats_sibling += 1
                elif asset.layer_found == 3:
                    stats_system += 1
                elif asset.layer_found == 4:
                    stats_network += 1
                elif asset.layer_found == 5:
                    stats_search += 1

                # Check for gates
                if non_cache_layer_used is None:
                    non_cache_layer_used = f"Layer {asset.layer_found}: {asset.source}"
                if asset.layer_found >= 4 and network_layer_used is None:
                    network_layer_used = f"Layer {asset.layer_found}: {asset.source}"

            print(
                f"[✅ {status_layer}] {f:<20} → {str(asset.file_path):<50} ({hunter_name})"
            )
        except Exception:
            missing_fonts.append(f)
            print(f"[❌   ] {f:<20} → NOT FOUND — tried 10 hunters")

    print("")
    print("════════════════════════════════════════")
    print("STEP 3: Preparing mkvmerge command")
    print("════════════════════════════════════════")

    # Output path
    output_path = episode_path.parent / f"{episode_path.stem}_verified.mkv"

    # Build mkvmerge command args
    mkvmerge_cmd = [
        "mkvmerge",
        "-o",
        str(output_path),
        str(episode_path),
        str(subtitle_path),
    ]

    for asset in resolved_assets:
        f_path = Path(asset.file_path)
        mime = get_font_mime_type(f_path.suffix)
        mkvmerge_cmd.extend(
            [
                "--attachment-name",
                f_path.name,
                "--attachment-mime-type",
                mime,
                "--attach-file",
                str(f_path),
            ]
        )

    print("mkvmerge args that would be used:")
    for i in range(0, len(mkvmerge_cmd)):
        cmd_part = mkvmerge_cmd[i]
        if cmd_part.startswith("--"):
            print(f"  {cmd_part} {mkvmerge_cmd[i + 1]}")
    print(f"\nFull Command:\n{' '.join(mkvmerge_cmd)}\n")

    mkvinfo_attachments: list[dict[str, str]] = []

    mkvmerge_available = "mkvmerge" in tool_registry

    if args.dry_run:
        print("Skipping mux (Dry-Run mode enabled).")
    else:
        print("════════════════════════════════════════")
        print("STEP 4: Running mkvmerge and mkvinfo")
        print("════════════════════════════════════════")
        if not mkvmerge_available:
            print("Warning: mkvmerge tool not found in tool registry. Skipping step 4.")
        else:
            print(f"Executing mux to: {output_path}")
            mux_result = await subprocess_adapter.execute(mkvmerge_cmd, timeout=300.0)
            if not mux_result.success:
                print(f"Error: mkvmerge failed with exit code {mux_result.exit_code}")
                print(mux_result.stderr)
            else:
                print("Mux complete! Running mkvinfo verification...")
                # Discover mkvinfo path in same folder as mkvmerge
                mkvmerge_tool = tool_registry.get("mkvmerge")
                mkvinfo_path = "mkvinfo"
                if mkvmerge_tool and mkvmerge_tool.is_available:
                    mkvinfo_exe = mkvmerge_tool.path.parent / (
                        "mkvinfo.exe" if sys.platform == "win32" else "mkvinfo"
                    )
                    if mkvinfo_exe.is_file():
                        mkvinfo_path = str(mkvinfo_exe)

                mkvinfo_result = await subprocess_adapter.execute(
                    [mkvinfo_path, str(output_path)], timeout=30.0
                )
                if mkvinfo_result.success:
                    mkvinfo_attachments = parse_mkvinfo_attachments(
                        mkvinfo_result.stdout
                    )
                    print("\nAttachments in output MKV:\n")
                    for att in mkvinfo_attachments:
                        print(
                            f"  {att.get('name', 'Unknown')} ({att.get('mime', 'Unknown')}) {att.get('size', 'Unknown size')}"
                        )
                else:
                    print(
                        f"Warning: mkvinfo failed to inspect output: {mkvinfo_result.stderr}"
                    )

    print("")
    print("════════════════════════════════════════")
    print("STEP 5: Final Verdict")
    print("════════════════════════════════════════")
    print(f"Fonts in subtitle:    {len(fonts_in_sub)}")
    resolved_pct = (
        (len(resolved_assets) / len(fonts_in_sub) * 100.0) if fonts_in_sub else 0.0
    )
    print(f"Fonts resolved:       {len(resolved_assets)}  ({resolved_pct:.1f}%)")
    print(f"└─ Cache (L0):       {stats_cache}")
    print(f"└─ MkvExtract (L1):  {stats_mkv}")
    print(f"└─ Sibling (L2):     {stats_sibling}")
    print(f"└─ System (L3):      {stats_system}")
    print(f"└─ Network (L4+):    {stats_network}")
    print(f"└─ SearchEngine (L5): {stats_search}")

    missing_pct = (
        (len(missing_fonts) / len(fonts_in_sub) * 100.0) if fonts_in_sub else 0.0
    )
    print(
        f"Fonts missing:         {len(missing_fonts)}  ({missing_pct:.1f}%)"
        + (f"  ({', '.join(missing_fonts)})" if missing_fonts else "")
    )
    print(f"Fonts in output MKV:  {len(mkvinfo_attachments)}  ← mkvinfo confirmed")

    print("\nConstitution E2E Gate:")
    if non_cache_layer_used:
        print(f"[✅] Non-cache layer resolved at least 1 font ({non_cache_layer_used})")
    else:
        print("[❌] No non-cache layers used")

    if not args.dry_run and len(mkvinfo_attachments) > 0:
        print("[✅] mkvinfo confirms font attachments in output MKV")
    elif args.dry_run:
        print("[🟡] mkvinfo check skipped in dry-run mode")
    else:
        print("[❌] mkvinfo did not confirm any font attachments in output MKV")

    if network_layer_used:
        print(f"[✅] Network layer (L4+) used ({network_layer_used})")
    else:
        print("[❌] No network layer (L4+) used — needs episode with non-system font")
    print("════════════════════════════════════════")


if __name__ == "__main__":
    asyncio.run(main())
