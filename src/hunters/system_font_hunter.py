import asyncio
import sys
import time
from pathlib import Path
from fontTools.ttLib import TTFont  # type: ignore[import-untyped]
import structlog

from src.models.font import FontQuery, FontAsset, HunterResult, FontPayload

logger = structlog.get_logger()


def _get_system_font_dirs() -> list[Path]:
    if sys.platform == "win32":
        return [
            Path("C:/Windows/Fonts"),
            Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
        ]
    elif sys.platform == "darwin":
        return [
            Path.home() / "Library/Fonts",
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
        ]
    else:  # Linux/BSD
        return [
            Path.home() / ".local/share/fonts",
            Path("/usr/local/share/fonts"),
            Path("/usr/share/fonts"),
        ]


def _extract_font_names(
    font_path: Path, font_number: int = 0
) -> tuple[str, dict[int, str], set[str]]:
    """
    Extract searchable font names and all nameids from a font file.
    Returns: (primary_name, nameids_dict, searchable_names_set)
    """
    searchable_names: set[str] = set()
    nameids: dict[int, str] = {}
    primary_name = font_path.stem

    try:
        font = TTFont(font_path, fontNumber=font_number)
        name_table = font["name"]

        for name_id in (1, 4, 6, 16):
            # Windows, Unicode BMP, English
            record = name_table.getName(name_id, 3, 1, 0x0409)
            if record:
                val = record.toUnicode().strip()
                nameids[name_id] = val
                searchable_names.add(val.lower())

            # Mac, Roman, English
            record = name_table.getName(name_id, 1, 0, 0)
            if record:
                val = record.toUnicode().strip()
                nameids[name_id] = val
                searchable_names.add(val.lower())

        font.close()

        if 4 in nameids:
            primary_name = nameids[4]
        elif 1 in nameids:
            primary_name = nameids[1]

    except Exception as e:
        logger.debug(
            "Failed to extract font names",
            path=str(font_path),
            font_number=font_number,
            error=str(e),
        )

    return primary_name, nameids, searchable_names


FONT_EXTENSIONS = frozenset({".ttf", ".otf", ".ttc"})

STRIP_SUFFIXES = frozenset(
    {
        "regular",
        "normal",
        "book",
        "roman",
        "plain",
        "standard",
        "medium",
        "text",
        "display",
    }
)

WEIGHT_SYNONYMS = {
    "semibold": {"demibold", "demi bold", "semi bold"},
    "bold": {"heavy", "black", "dark"},
    "light": {"thin", "hairline", "ultralight", "extra light", "extralight"},
    "extrabold": {"ultra bold", "ultrabold", "extra bold"},
}


class SystemFontHunter:
    name: str = "SystemFontHunter"
    priority: int = 3
    rate_limit: float = 0.0
    circuit_breaker_threshold: int = 3
    ping_url: str | None = None

    def __init__(self) -> None:
        self._index: dict[str, tuple[Path, str, dict[int, str]]] = {}
        self._index_built: bool = False

    def supports(self, query: FontQuery) -> bool:
        return True

    def _strip_style_suffix(self, name: str) -> str:
        """Strip trailing style suffixes like 'regular', 'normal', 'book' from the end of a name."""
        tokens = name.split()
        while tokens and tokens[-1] in STRIP_SUFFIXES:
            tokens.pop()
        return " ".join(tokens)

    def _make_result(
        self, index_key: str, query: FontQuery, duration_ms: float
    ) -> HunterResult:
        path, primary_name, nameids = self._index[index_key]
        asset = FontAsset(
            name=primary_name,
            file_path=path,
            source="system",
            layer_found=self.priority,
            cache_hit=False,
            nameids=nameids,
            is_cacheable=False,
        )
        return HunterResult(
            query=query,
            font_asset=asset,
            success=True,
            hunter_name=self.name,
            duration_ms=duration_ms,
            attempts=1,
        )

    def _build_index(self) -> None:
        """Scan system directories and index all valid fonts."""
        if self._index_built:
            return

        logger.info("Building system font index...")
        start_time = time.perf_counter()

        dirs = _get_system_font_dirs()
        indexed_count = 0

        for d in dirs:
            logger.debug(f"Scanning dir: {d}")
            if not d.exists():
                logger.debug("System font directory does not exist", path=str(d))
                logger.debug(f"No match in {d}")
                continue

            found_any = False
            try:
                for p in d.rglob("*"):
                    if p.is_file() and p.suffix.lower() in FONT_EXTENSIONS:
                        found_any = True
                        logger.debug(f"Candidate found: {p}")
                        if p.suffix.lower() == ".ttc":
                            try:
                                from fontTools.ttLib import TTCollection

                                collection = TTCollection(str(p))
                                num_fonts = len(collection.fonts)
                                collection.close()
                            except Exception:
                                num_fonts = 1

                            for i in range(num_fonts):
                                try:
                                    primary_name, nameids, searchable_names = (
                                        _extract_font_names(p, font_number=i)
                                    )
                                    if searchable_names:
                                        for s_name in searchable_names:
                                            if s_name not in self._index:
                                                self._index[s_name] = (
                                                    p,
                                                    primary_name,
                                                    nameids,
                                                )
                                            # T029: Also index a version with style suffix stripped
                                            stripped = self._strip_style_suffix(s_name)
                                            if (
                                                stripped != s_name
                                                and stripped not in self._index
                                            ):
                                                self._index[stripped] = (
                                                    p,
                                                    primary_name,
                                                    nameids,
                                                )
                                        indexed_count += 1
                                except Exception as e:
                                    logger.debug(
                                        "Failed to extract TTC font",
                                        path=str(p),
                                        font_number=i,
                                        error=str(e),
                                    )
                        else:
                            primary_name, nameids, searchable_names = (
                                _extract_font_names(p)
                            )
                            if searchable_names:
                                for s_name in searchable_names:
                                    if s_name not in self._index:
                                        self._index[s_name] = (p, primary_name, nameids)
                                    # T029: Also index a version with style suffix stripped
                                    stripped = self._strip_style_suffix(s_name)
                                    if (
                                        stripped != s_name
                                        and stripped not in self._index
                                    ):
                                        self._index[stripped] = (
                                            p,
                                            primary_name,
                                            nameids,
                                        )
                                indexed_count += 1
                if not found_any:
                    logger.debug(f"No match in {d}")
            except Exception as e:
                logger.warning(
                    "Error scanning system font directory",
                    path=str(d),
                    error=str(e),
                )
                if not found_any:
                    logger.debug(f"No match in {d}")

        duration = time.perf_counter() - start_time
        logger.info(
            "System font index built",
            indexed_fonts=indexed_count,
            duration_s=duration,
        )
        self._index_built = True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        """Search system fonts for a match with progressive normalization tiers."""
        logger.debug(f"SystemFontHunter called with query={query.requested_name}")
        if not self._index_built:
            await asyncio.to_thread(self._build_index)

        requested = query.requested_name.strip().lower()
        start_time = time.perf_counter()

        # 1. Exact match (existing behavior, fast path)
        if requested in self._index:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            result = self._make_result(requested, query, duration_ms)
            asset = result.font_asset
            assert asset is not None
            logger.info(
                "System font match found (tier 1: exact)",
                requested_name=query.requested_name,
                matched_name=asset.name,
                path=str(asset.file_path),
            )
            return [result]

        # 2. Strip trailing style suffixes
        normalized = self._strip_style_suffix(requested)
        if normalized != requested and normalized in self._index:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            result = self._make_result(normalized, query, duration_ms)
            asset = result.font_asset
            assert asset is not None
            logger.info(
                "System font match found (tier 2: stripped suffix)",
                requested_name=query.requested_name,
                matched_name=asset.name,
                path=str(asset.file_path),
            )
            return [result]

        # 3. Try appending common suffixes if requested name is a bare family
        for suffix in STRIP_SUFFIXES:
            candidate = f"{requested} {suffix}"
            if candidate in self._index:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                result = self._make_result(candidate, query, duration_ms)
                asset = result.font_asset
                assert asset is not None
                logger.info(
                    "System font match found (tier 3: appended suffix)",
                    requested_name=query.requested_name,
                    matched_name=asset.name,
                    path=str(asset.file_path),
                )
                return [result]

        # 4. Weight synonym expansion
        for canonical, synonyms in WEIGHT_SYNONYMS.items():
            for syn in synonyms:
                if syn in requested:
                    candidate = requested.replace(syn, canonical)
                    if candidate in self._index:
                        duration_ms = (time.perf_counter() - start_time) * 1000.0
                        result = self._make_result(candidate, query, duration_ms)
                        asset = result.font_asset
                        assert asset is not None
                        logger.info(
                            "System font match found (tier 4: weight synonym)",
                            requested_name=query.requested_name,
                            matched_name=asset.name,
                            path=str(asset.file_path),
                        )
                        return [result]

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info("System font miss", requested_name=query.requested_name)
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        raise NotImplementedError(
            "SystemFontHunter resolves fonts in-place; download is not supported."
        )
