import asyncio
import urllib.parse
import re
import httpx
import time
from pathlib import Path
import structlog

from src.models.font import FontQuery, FontAsset, HunterResult, FontPayload
from src.hunters.sources._hunter_utils import (
    verify_font,
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

BLOCKED_DOMAINS = frozenset(
    {
        "pinterest.com",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "twitter.com",
        "x.com",
        "freefontsfamily.com",
    }
)


def is_blocked(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        for blocked in BLOCKED_DOMAINS:
            if netloc == blocked or netloc.endswith("." + blocked):
                return True
    except Exception:
        pass
    return False


class SearchEngineHunter:
    name: str = "SearchEngineHunter"
    priority: int = 5
    rate_limit: float = 2.0
    circuit_breaker_threshold: int = 3
    ping_url: str | None = "https://html.duckduckgo.com"

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy
        self._cache: dict[str, FontPayload] = {}
        self._result_cache: dict[str, HunterResult] = {}

    def supports(self, query: FontQuery) -> bool:
        return True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        logger.debug("SearchEngineHunter search start", requested=query.requested_name)
        normalized = normalize_font_name(query.requested_name)
        if normalized in self._result_cache:
            return [self._result_cache[normalized]]

        start_time = time.perf_counter()
        search_query = f"{query.requested_name} font free download ttf"
        encoded_query = urllib.parse.quote(search_query)
        search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        proxy = self._proxy if self._proxy else None
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
                proxy=proxy,
            ) as client:
                resp = await client.get(search_url, follow_redirects=True)
                resp.raise_for_status()

                # Extract URLs from uddg parameter
                raw_urls = re.findall(r'uddg=([^&"]+)', resp.text)
                actual_urls = []
                for u in raw_urls:
                    decoded_url = urllib.parse.unquote(u)
                    if not is_blocked(decoded_url) and decoded_url not in actual_urls:
                        actual_urls.append(decoded_url)

                if not actual_urls:
                    logger.debug(
                        "No search result URLs found on DuckDuckGo",
                        family=query.requested_name,
                    )
                    return []

                # Limit to top 10 results
                for target_url in actual_urls[:10]:
                    await asyncio.sleep(self.rate_limit)

                    logger.debug("Crawling search result page", url=target_url)
                    try:
                        page_resp = await client.get(target_url, follow_redirects=True)
                        if page_resp.status_code != 200:
                            continue

                        # Look for direct links matching .ttf, .otf, .ttc, or .zip
                        hrefs = re.findall(
                            r'href=["\']([^"\']+\.(?:ttf|otf|ttc|zip))["\']',
                            page_resp.text,
                            re.IGNORECASE,
                        )
                        resolved_links = []
                        for h in hrefs:
                            full_url = urllib.parse.urljoin(target_url, h)
                            if full_url not in resolved_links:
                                resolved_links.append(full_url)

                        # Try first few links on this page (max 5)
                        for link in resolved_links[:5]:
                            await asyncio.sleep(self.rate_limit)
                            logger.debug("Downloading candidate font link", url=link)
                            try:
                                dl_resp = await client.get(link, follow_redirects=True)
                                if dl_resp.status_code != 200:
                                    continue

                                matched_font = None
                                if link.lower().endswith(".zip"):
                                    fonts = extract_fonts_from_zip(dl_resp.content)
                                    for filename, font_bytes, nameids in fonts:
                                        if font_name_matches(
                                            query.requested_name, nameids
                                        ):
                                            matched_font = (
                                                filename,
                                                font_bytes,
                                                nameids,
                                            )
                                            break
                                else:
                                    # Direct font file (.ttf / .otf / .ttc)
                                    filename = Path(
                                        urllib.parse.urlparse(link).path
                                    ).name
                                    direct_nameids = verify_font(
                                        dl_resp.content, filename
                                    )
                                    if direct_nameids and font_name_matches(
                                        query.requested_name, direct_nameids
                                    ):
                                        matched_font = (
                                            filename,
                                            dl_resp.content,
                                            direct_nameids,
                                        )

                                if matched_font:
                                    filename, font_bytes, nameids = matched_font
                                    primary_name = (
                                        nameids.get(4)
                                        or nameids.get(1)
                                        or Path(filename).stem
                                    )

                                    payload = FontPayload(
                                        font_name=primary_name,
                                        font_data=font_bytes,
                                        file_extension=Path(filename).suffix.lower(),
                                        source=self.name,
                                        nameids=nameids,
                                        metadata={
                                            "url": link,
                                            "source_page": target_url,
                                        },
                                    )

                                    self._cache[normalized] = payload
                                    duration_ms = (
                                        time.perf_counter() - start_time
                                    ) * 1000.0

                                    asset = FontAsset(
                                        name=primary_name,
                                        file_path=Path("search_engine") / filename,
                                        source=self.name,
                                        layer_found=self.priority,
                                        cache_hit=False,
                                        nameids=nameids,
                                        is_cacheable=True,
                                    )

                                    logger.info(
                                        "SearchEngine matched and downloaded",
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
                                    "Failed to download/verify link",
                                    url=link,
                                    error=str(e),
                                )

                    except Exception as e:
                        logger.debug(
                            "Failed crawling page", url=target_url, error=str(e)
                        )

        except Exception as e:
            logger.debug(
                "SearchEngine request failed",
                family=query.requested_name,
                error=str(e),
            )
            raise

        logger.debug("SearchEngine font miss", requested_name=query.requested_name)
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        normalized = normalize_font_name(result.query.requested_name)
        payload = self._cache.get(normalized)
        if not payload:
            raise ValueError("Download called without successful search first")
        return payload
