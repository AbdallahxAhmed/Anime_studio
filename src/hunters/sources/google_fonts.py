import urllib.parse
import httpx
import time
from pathlib import Path
import structlog

from src.models.font import FontQuery, FontAsset, HunterResult, FontPayload
from src.hunters.sources._hunter_utils import (
    extract_fonts_from_zip,
    font_name_matches,
)

logger = structlog.get_logger()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class GoogleFontsHunter:
    name: str = "GoogleFontsHunter"
    priority: int = 4
    rate_limit: float = 0.5
    circuit_breaker_threshold: int = 3
    ping_url: str | None = "https://fonts.google.com"

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy
        self._cache: dict[str, FontPayload] = {}

    def supports(self, query: FontQuery) -> bool:
        return True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        logger.debug("GoogleFontsHunter search start", requested=query.requested_name)
        start_time = time.perf_counter()

        encoded_name = urllib.parse.quote(query.requested_name)
        url = f"https://fonts.google.com/download?family={encoded_name}"

        proxy = self._proxy if self._proxy else None
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
                proxy=proxy,
            ) as client:
                resp = await client.get(url, follow_redirects=True)

                if resp.status_code == 404:
                    logger.debug(
                        "Google Fonts family not found", family=query.requested_name
                    )
                    return []

                resp.raise_for_status()

                # Extract and verify zip contents
                fonts = extract_fonts_from_zip(resp.content)
                if not fonts:
                    logger.debug(
                        "No valid fonts found in Google Fonts zip",
                        family=query.requested_name,
                    )
                    return []

                # Find the best match
                matched_font = None
                for filename, font_bytes, nameids in fonts:
                    if font_name_matches(query.requested_name, nameids):
                        matched_font = (filename, font_bytes, nameids)
                        break

                if not matched_font:
                    # Fallback: take the first one if name match is slightly different or check exact matching
                    # But the task says: match requested name against extracted fonts via font_name_matches()
                    logger.debug(
                        "No exact font name match in Google Fonts zip",
                        family=query.requested_name,
                    )
                    return []

                filename, font_bytes, nameids = matched_font
                primary_name = nameids.get(4) or nameids.get(1) or Path(filename).stem

                payload = FontPayload(
                    font_name=primary_name,
                    font_data=font_bytes,
                    file_extension=Path(filename).suffix.lower(),
                    source=self.name,
                    nameids=nameids,
                    metadata={"url": url},
                )

                self._cache[query.requested_name] = payload
                duration_ms = (time.perf_counter() - start_time) * 1000.0

                asset = FontAsset(
                    name=primary_name,
                    file_path=Path("google_fonts") / filename,
                    source=self.name,
                    layer_found=self.priority,
                    cache_hit=False,
                    nameids=nameids,
                    is_cacheable=True,
                )

                logger.info(
                    "Google Fonts matched and downloaded",
                    requested_name=query.requested_name,
                    matched_name=primary_name,
                )

                return [
                    HunterResult(
                        query=query,
                        font_asset=asset,
                        success=True,
                        hunter_name=self.name,
                        duration_ms=duration_ms,
                        attempts=1,
                    )
                ]

        except Exception as e:
            logger.debug(
                "Google Fonts request failed",
                family=query.requested_name,
                error=str(e),
            )
            raise

    async def download(self, result: HunterResult) -> FontPayload:
        payload = self._cache.get(result.query.requested_name)
        if not payload:
            raise ValueError("Download called without successful search first")
        return payload
