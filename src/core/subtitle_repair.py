import re
from pathlib import Path
import structlog
from src.models.font import FontQuery
from src.errors import EncodingRepairError

logger = structlog.get_logger()


def _normalize_font_name(raw_name: str) -> str:
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
            # Check if suffix is at the end of the string
            if match and name[match.end() :].strip() == "":
                name = name[: match.start()].strip()
                changed = True
                break

    logger.debug("Normalized font name", original=raw_name, normalized=name)
    return name


def repair_ass(path: Path) -> str:
    """Read ASS file, validate structure, defensively skip malformed styles, return content."""
    logger.info("Starting ASS file repair", path=str(path))
    content = path.read_text(encoding="utf-8")
    if "[V4+ Styles]" not in content:
        logger.error("Missing [V4+ Styles] section", path=str(path))
        raise EncodingRepairError("Missing [V4+ Styles] section in ASS file.")

    lines = content.splitlines()
    repaired_lines = []
    in_styles = False
    format_fields_count = 0

    for line in lines:
        stripped = line.strip()
        if stripped == "[V4+ Styles]":
            in_styles = True
            repaired_lines.append(line)
            continue
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_styles = False
            repaired_lines.append(line)
            continue

        if in_styles:
            if stripped.startswith("Format:"):
                fields = [f.strip() for f in stripped[7:].split(",")]
                format_fields_count = len(fields)
                repaired_lines.append(line)
            elif stripped.startswith("Style:"):
                # Split style parameters (after Style:)
                values = [v.strip() for v in stripped[6:].split(",")]
                if format_fields_count > 0 and len(values) != format_fields_count:
                    logger.warning(
                        "Skipping malformed style line",
                        line=stripped,
                        expected_fields=format_fields_count,
                        found_fields=len(values),
                    )
                    continue
                repaired_lines.append(line)
            else:
                repaired_lines.append(line)
        else:
            repaired_lines.append(line)

    logger.info("ASS file repair complete", path=str(path))
    return "\n".join(repaired_lines)


def extract_fonts(
    content: str, episode_path: Path, anime_title: str
) -> list[FontQuery]:
    """Extract font references from ASS [V4+ Styles] section and normalize them."""
    if "[V4+ Styles]" not in content:
        return []

    lines = content.splitlines()
    in_styles = False
    fontname_idx = -1
    fonts = set()

    for line in lines:
        stripped = line.strip()
        if stripped == "[V4+ Styles]":
            in_styles = True
            continue
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_styles = False
            continue

        if in_styles:
            if stripped.startswith("Format:"):
                fields = [f.strip().lower() for f in stripped[7:].split(",")]
                if "fontname" in fields:
                    fontname_idx = fields.index("fontname")
            elif stripped.startswith("Style:") and fontname_idx >= 0:
                values = [v.strip() for v in stripped[6:].split(",")]
                if len(values) > fontname_idx:
                    raw_name = values[fontname_idx]
                    norm_name = _normalize_font_name(raw_name)
                    if norm_name:
                        fonts.add(norm_name)

    queries = [
        FontQuery(requested_name=f, anime_title=anime_title, episode_path=episode_path)
        for f in sorted(list(fonts))
    ]
    logger.info("Extracted unique fonts from ASS content", font_count=len(queries))
    return queries
