import asyncio
import urllib.parse
import re
import httpx
import time
from pathlib import Path
import structlog

from src.models.font import FontQuery, FontAsset, HunterResult, FontPayload
from src.hunters.sources._hunter_utils import (
    extract_fonts_from_zip,
    font_name_matches,
    normalize_font_name,
)

logger = structlog.get_logger()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class FontSpaceHunter:
    name: str = "FontSpaceHunter"
    priority: int = 4
    rate_limit: float = 1.0
    circuit_breaker_threshold: int = 3
    ping_url: str | None = "https://www.fontspace.com"

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy
        self._cache: dict[str, FontPayload] = {}
        self._result_cache: dict[str, HunterResult] = {}

    def supports(self, query: FontQuery) -> bool:
        return True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        logger.debug("FontSpaceHunter search start", requested=query.requested_name)
        normalized = normalize_font_name(query.requested_name)
        if normalized in self._result_cache:
            return [self._result_cache[normalized]]

        start_time = time.perf_counter()
        encoded_name = urllib.parse.quote(query.requested_name)
        search_url = f"https://www.fontspace.com/search?q={encoded_name}"

        proxy = self._proxy if self._proxy else None
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
                proxy=proxy,
            ) as client:
                resp = await client.get(search_url, follow_redirects=True)
                resp.raise_for_status()

                # Find all download links on page
                slugs = re.findall(r"/download/([a-zA-Z0-9_\-]+)", resp.text)
                # Deduplicate slugs
                unique_slugs = []
                for s in slugs:
                    if s not in unique_slugs:
                        unique_slugs.append(s)

                if not unique_slugs:
                    logger.debug(
                        "No slugs found on FontSpace search page",
                        family=query.requested_name,
                    )
                    return []

                # Try first few slugs (max 3)
                for slug in unique_slugs[:3]:
                    await asyncio.sleep(self.rate_limit)

                    download_url = f"https://www.fontspace.com/download/{slug}"
                    logger.debug(
                        "Downloading font archive from FontSpace", url=download_url
                    )

                    download_resp = await client.get(
                        download_url, follow_redirects=True
                    )
                    if download_resp.status_code != 200:
                        continue

                    fonts = extract_fonts_from_zip(download_resp.content)
                    if not fonts:
                        continue

                    matched_font = None
                    for filename, font_bytes, nameids in fonts:
                        if font_name_matches(query.requested_name, nameids):
                            matched_font = (filename, font_bytes, nameids)
                            break

                    if matched_font:
                        filename, font_bytes, nameids = matched_font
                        primary_name = (
                            nameids.get(4) or nameids.get(1) or Path(filename).stem
                        )

                        payload = FontPayload(
                            font_name=primary_name,
                            font_data=font_bytes,
                            file_extension=Path(filename).suffix.lower(),
                            source=self.name,
                            nameids=nameids,
                            metadata={"url": download_url, "slug": slug},
                        )

                        self._cache[normalized] = payload
                        duration_ms = (time.perf_counter() - start_time) * 1000.0

                        asset = FontAsset(
                            name=primary_name,
                            file_path=Path("fontspace") / filename,
                            source=self.name,
                            layer_found=self.priority,
                            cache_hit=False,
                            nameids=nameids,
                            is_cacheable=True,
                        )

                        logger.info(
                            "FontSpace matched and downloaded",
                            requested_name=query.requested_name,
                            matched_name=primary_name,
                        )

                        hunter_result = HunterResult(
                            query=query,
                            font_asset=asset,
                            success=True,
                            hunter_name=self.name,
                            duration_ms=duration_ms,
                            attempts=1,
                        )
                        self._result_cache[normalized] = hunter_result
                        return [hunter_result]

        except Exception as e:
            logger.debug(
                "FontSpace request failed",
                family=query.requested_name,
                error=str(e),
            )
            raise

        logger.debug("FontSpace font miss", requested_name=query.requested_name)
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        normalized = normalize_font_name(result.query.requested_name)
        payload = self._cache.get(normalized)
        if not payload:
            raise ValueError("Download called without successful search first")
        return payload
