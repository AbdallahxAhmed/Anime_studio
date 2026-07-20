from typing import Any
import structlog
import tomllib
from datetime import datetime
from pathlib import Path
from src.config import CACHE_VERSION
from src.models.font import FontPayload, FontAsset

logger = structlog.get_logger()


class FontCache:
    """Persistent on-disk font cache with TOML index."""

    def __init__(self, cache_dir: Path | str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / "font_library.toml"
        self.index: dict[str, Any] = self._load_index()

    def _load_index(self) -> dict[str, Any]:
        """Load and validate the cache TOML index. Rebuilds on error or version mismatch."""
        if not self.index_path.is_file():
            logger.info(
                "TOML index missing, scanning directory", path=str(self.index_path)
            )
            return self._rebuild_from_scan()

        try:
            with self.index_path.open("rb") as f:
                data = tomllib.load(f)

            if data.get("cache_version") != CACHE_VERSION:
                logger.warning(
                    "Cache version mismatch. Rebuilding.",
                    expected=CACHE_VERSION,
                    found=data.get("cache_version"),
                )
                return self._rebuild_from_scan()

            # Ensure fonts exists
            if "fonts" not in data:
                data["fonts"] = {}
            return data
        except Exception as e:
            logger.warning(
                "Corrupt or invalid TOML index. Rebuilding from scan.", error=str(e)
            )
            return self._rebuild_from_scan()

    def _save_index(self, index: dict[str, Any]) -> None:
        """Atomically save index to font_library.toml using manual TOML serialization."""
        logger.debug("Saving TOML index", path=str(self.index_path))
        lines = []
        lines.append(f'cache_version = "{index.get("cache_version", CACHE_VERSION)}"\n')

        fonts = index.get("fonts", {})
        for font_name, entry in fonts.items():
            lines.append(f'[fonts."{font_name}"]')
            lines.append(f'file = "{entry["file"]}"')
            lines.append(f'source = "{entry["source"]}"')
            lines.append(f"layer_found = {entry['layer_found']}")
            lines.append(f'added = "{entry["added"]}"')

            # Format nameids as inline table
            nameids = entry.get("nameids", {})
            formatted_pairs = []
            for k, v in nameids.items():
                escaped_val = str(v).replace('"', '\\"')
                formatted_pairs.append(f'{k} = "{escaped_val}"')
            nameids_str = ", ".join(formatted_pairs)
            lines.append(f"nameids = {{{nameids_str}}}")
            lines.append("")

        temp_file = self.index_path.with_suffix(".tmp")
        try:
            temp_file.write_text("\n".join(lines), encoding="utf-8")
            temp_file.replace(self.index_path)
        except Exception as e:
            logger.error("Failed to write TOML index atomically", error=str(e))
            if temp_file.exists():
                temp_file.unlink()
            raise

    def _rebuild_from_scan(self) -> dict[str, Any]:
        """Rebuild the index by scanning files inside cache_dir."""
        logger.info("Scanning cache directory for font files", dir=str(self.cache_dir))
        index: dict[str, Any] = {
            "cache_version": CACHE_VERSION,
            "fonts": {},
        }

        # Scan for existing font files
        valid_extensions = {".ttf", ".otf", ".woff", ".woff2"}
        for item in self.cache_dir.iterdir():
            if item.is_file() and item.suffix.lower() in valid_extensions:
                font_name = item.stem
                index["fonts"][font_name] = {
                    "file": item.name,
                    "source": "scanned",
                    "layer_found": 0,
                    "added": datetime.now().isoformat(),
                    "nameids": {},
                }

        self._save_index(index)
        return index

    def lookup(self, font_name: str) -> FontAsset | None:
        """Look up a font by name in the index."""
        fonts = self.index.get("fonts", {})
        if font_name not in fonts:
            logger.info("Cache miss", font_name=font_name)
            return None

        entry = fonts[font_name]
        file_path = self.cache_dir / entry["file"]
        if not file_path.is_file():
            logger.warning(
                "Cache index refers to missing file",
                font_name=font_name,
                path=str(file_path),
            )
            return None

        # Convert back string keys in nameids to ints
        nameids = {int(k): str(v) for k, v in entry.get("nameids", {}).items()}

        logger.info("Cache hit", font_name=font_name, path=str(file_path))
        return FontAsset(
            name=font_name,
            file_path=file_path,
            source=entry["source"],
            layer_found=entry["layer_found"],
            cache_hit=True,
            nameids=nameids,
        )

    def store(self, payload: FontPayload, layer_found: int) -> FontAsset:
        """Atomically store a new font in the cache and update index."""
        ext = payload.file_extension.strip()
        if not ext.startswith("."):
            ext = f".{ext}"

        filename = f"{payload.font_name}{ext}"
        final_path = self.cache_dir / filename

        # Atomic write of font data
        temp_path = self.cache_dir / f"{filename}.tmp"
        try:
            temp_path.write_bytes(payload.font_data)
            temp_path.replace(final_path)
        except Exception as e:
            logger.error(
                "Failed to write font data atomically",
                path=str(final_path),
                error=str(e),
            )
            if temp_path.exists():
                temp_path.unlink()
            raise

        # Update index
        self.index["fonts"][payload.font_name] = {
            "file": filename,
            "source": payload.source,
            "layer_found": layer_found,
            "added": datetime.now().isoformat(),
            "nameids": {str(k): v for k, v in payload.nameids.items()},
        }
        self._save_index(self.index)

        logger.info(
            "Font stored in cache", font_name=payload.font_name, path=str(final_path)
        )
        return FontAsset(
            name=payload.font_name,
            file_path=final_path,
            source=payload.source,
            layer_found=layer_found,
            cache_hit=False,
            nameids=payload.nameids,
        )
