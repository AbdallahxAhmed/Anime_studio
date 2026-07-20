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


class BeFontsHunter:
    name: str = "BeFontsHunter"
    priority: int = 4
    rate_limit: float = 1.0
    circuit_breaker_threshold: int = 3
    ping_url: str | None = "https://befonts.com"

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy
        self._cache: dict[str, FontPayload] = {}
        self._result_cache: dict[str, HunterResult] = {}

    def supports(self, query: FontQuery) -> bool:
        return True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        logger.debug("BeFontsHunter search start", requested=query.requested_name)
        normalized = normalize_font_name(query.requested_name)
        if normalized in self._result_cache:
            return [self._result_cache[normalized]]

        start_time = time.perf_counter()
        encoded_name = urllib.parse.quote(query.requested_name)
        search_url = f"https://befonts.com/?s={encoded_name}"

        proxy = self._proxy if self._proxy else None
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
                proxy=proxy,
            ) as client:
                resp = await client.get(search_url, follow_redirects=True)
                resp.raise_for_status()

                # Find post URLs (e.g., https://befonts.com/some-font-name.html)
                posts = re.findall(
                    r'href=["\'](https://befonts\.com/[a-zA-Z0-9\-]+(?:\.html)?)["\']',
                    resp.text,
                )
                unique_posts = []
                for p in posts:
                    # Filter out static/menu pages
                    if not any(
                        x in p.lower()
                        for x in (
                            "/category/",
                            "/author/",
                            "/tag/",
                            "/contact",
                            "/about",
                            "/terms",
                            "/privacy",
                        )
                    ):
                        if p not in unique_posts:
                            unique_posts.append(p)

                if not unique_posts:
                    logger.debug(
                        "No post URLs found on BeFonts search",
                        family=query.requested_name,
                    )
                    return []

                # Try the first few posts (max 2)
                for post_url in unique_posts[:2]:
                    await asyncio.sleep(self.rate_limit)

                    logger.debug("Fetching BeFonts post page", url=post_url)
                    post_resp = await client.get(post_url, follow_redirects=True)
                    if post_resp.status_code != 200:
                        continue

                    # Look for download page links (e.g., https://befonts.com/download/some-font)
                    dl_links = re.findall(
                        r'href=["\'](https://befonts\.com/download/[a-zA-Z0-9\-]+)["\']',
                        post_resp.text,
                    )
                    if not dl_links:
                        # Fallback: maybe relative link /download/slug
                        dl_links = re.findall(
                            r'href=["\'](/download/[a-zA-Z0-9\-]+)["\']', post_resp.text
                        )
                        dl_links = [f"https://befonts.com{lnk}" for lnk in dl_links]

                    if not dl_links:
                        # Try to find direct ZIP link in post page
                        zip_links = re.findall(
                            r'href=["\'](https://[a-zA-Z0-9\-./_]+\.zip)["\']',
                            post_resp.text,
                        )
                        if zip_links:
                            dl_links = [zip_links[0]]

                    if not dl_links:
                        continue

                    # Fetch the download page or direct zip link
                    dl_url = dl_links[0]
                    await asyncio.sleep(self.rate_limit)

                    logger.debug("Fetching BeFonts download/zip link", url=dl_url)

                    if dl_url.endswith(".zip"):
                        # Direct zip download
                        download_resp = await client.get(dl_url, follow_redirects=True)
                    else:
                        # Fetch download page and parse direct download link
                        dl_page_resp = await client.get(dl_url, follow_redirects=True)
                        if dl_page_resp.status_code != 200:
                            continue

                        # Find a link ending with .zip on this page
                        zip_matches = re.findall(
                            r'href=["\'](https://[a-zA-Z0-9\-./_]+\.zip)["\']',
                            dl_page_resp.text,
                        )
                        if not zip_matches:
                            # Try matching download buttons / links
                            zip_matches = re.findall(
                                r'href=["\'](https://befonts\.com/download-link[?a-zA-Z0-9\-=_.]+)["\']',
                                dl_page_resp.text,
                            )

                        if not zip_matches:
                            continue

                        await asyncio.sleep(self.rate_limit)
                        download_resp = await client.get(
                            zip_matches[0], follow_redirects=True
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
                            metadata={"url": dl_url, "post_url": post_url},
                        )

                        self._cache[normalized] = payload
                        duration_ms = (time.perf_counter() - start_time) * 1000.0

                        asset = FontAsset(
                            name=primary_name,
                            file_path=Path("befonts") / filename,
                            source=self.name,
                            layer_found=self.priority,
                            cache_hit=False,
                            nameids=nameids,
                            is_cacheable=True,
                        )

                        logger.info(
                            "BeFonts matched and downloaded",
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
                "BeFonts request failed",
                family=query.requested_name,
                error=str(e),
            )
            raise

        logger.debug("BeFonts font miss", requested_name=query.requested_name)
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        normalized = normalize_font_name(result.query.requested_name)
        payload = self._cache.get(normalized)
        if not payload:
            raise ValueError("Download called without successful search first")
        return payload
