import io
import zipfile
import structlog
from fontTools.ttLib import TTFont  # type: ignore[import-untyped]
from pathlib import Path

logger = structlog.get_logger()

FONT_EXTENSIONS = frozenset({".ttf", ".otf", ".ttc"})


def verify_font(data: bytes, filename: str) -> dict[int, str] | None:
    """Verify font data with fontTools. Returns nameids dict or None if invalid."""
    try:
        font = TTFont(io.BytesIO(data))
        nameids = {}
        for name_id in (1, 4, 6):
            # Windows, Unicode BMP, English
            record = font["name"].getName(name_id, 3, 1, 0x0409)
            if record:
                nameids[name_id] = record.toUnicode().strip()
        font.close()
        if nameids:
            return nameids
    except Exception as e:
        logger.warning(
            "Downloaded file is not a valid font, skipping",
            filename=filename,
            error=str(e),
        )
    return None


def extract_fonts_from_zip(data: bytes) -> list[tuple[str, bytes, dict[int, str]]]:
    """Extract font files from ZIP, verify each. Returns list of (filename, font_bytes, nameids)."""
    results = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if Path(name).suffix.lower() in FONT_EXTENSIONS:
                    try:
                        font_bytes = zf.read(name)
                        nameids = verify_font(font_bytes, name)
                        if nameids:
                            results.append((Path(name).name, font_bytes, nameids))
                    except Exception as e:
                        logger.warning(
                            "Failed to read/verify font from ZIP",
                            filename=name,
                            error=str(e),
                        )
    except Exception as e:
        logger.debug("ZIP extraction failed", error=str(e))
    return results


def normalize_font_name(name: str) -> str:
    """Normalize font name for comparison."""
    return name.strip().lower().replace("-", " ").replace("_", " ")


def font_name_matches(requested: str, candidate_nameids: dict[int, str]) -> bool:
    """Check if requested font name matches any nameID in candidate."""
    req = normalize_font_name(requested)
    for nid in (1, 4, 6):
        if nid in candidate_nameids:
            if normalize_font_name(candidate_nameids[nid]) == req:
                return True
    return False
