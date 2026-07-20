import asyncio
import json
import tempfile
import time
from pathlib import Path
import structlog

from src.models.font import FontQuery, FontAsset, HunterResult, FontPayload
from src.ports.subprocess import SubprocessPort
from src.hunters.sources._hunter_utils import (
    verify_font,
    font_name_matches,
    normalize_font_name,
)

logger = structlog.get_logger()


class MkvExtractHunter:
    name: str = "MkvExtractHunter"
    priority: int = 1
    rate_limit: float = 0.0
    circuit_breaker_threshold: int = 3
    ping_url: str | None = None

    def __init__(
        self, subprocess_port: SubprocessPort, library_path: Path | None = None
    ) -> None:
        self._subprocess_port = subprocess_port
        self._library_path = library_path
        self._scanned: bool = False
        self._attachments: list[tuple[Path, int, str]] = []
        # List of (mkv_path, attachment_id, original_filename)
        self._cache: dict[str, FontPayload] = {}
        self._result_cache: dict[str, HunterResult] = {}

    def supports(self, query: FontQuery) -> bool:
        return True

    async def _scan_library(self) -> None:
        if self._scanned or not self._library_path:
            self._scanned = True
            return

        logger.info("Scanning library MKV files for fonts...")

        def find_mkvs(lib_path: Path) -> list[Path]:
            try:
                mkvs = []
                for p in lib_path.rglob("*.mkv"):
                    if not any(
                        part.startswith(".") for part in p.relative_to(lib_path).parts
                    ):
                        mkvs.append(p)
                return mkvs
            except Exception:
                return []

        mkv_paths = await asyncio.to_thread(find_mkvs, self._library_path)

        for mkv_path in mkv_paths:
            try:
                result = await self._subprocess_port.execute(
                    ["mkvmerge", "-J", str(mkv_path)], timeout=30.0
                )
                if result.success:
                    data = json.loads(result.stdout)
                    attachments = data.get("attachments", [])
                    for att in attachments:
                        filename = att.get("file_name", "")
                        content_type = att.get("content_type", "")
                        att_id = att.get("id")

                        if att_id is not None and (
                            filename.lower().endswith((".ttf", ".otf", ".ttc"))
                            or "font" in content_type.lower()
                        ):
                            self._attachments.append((mkv_path, att_id, filename))
            except Exception as e:
                logger.debug(
                    "Failed to scan attachments in MKV",
                    path=str(mkv_path),
                    error=str(e),
                )

        self._scanned = True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        logger.debug("MkvExtractHunter search start", requested=query.requested_name)

        normalized = normalize_font_name(query.requested_name)
        if normalized in self._result_cache:
            logger.debug(
                "MkvExtractHunter result cache hit", requested=query.requested_name
            )
            return [self._result_cache[normalized]]

        if not self._scanned:
            await self._scan_library()

        start_time = time.perf_counter()

        # Look through all attachments, extract and check internal names
        for mkv_path, att_id, filename in self._attachments:
            if not filename.lower().endswith((".ttf", ".otf", ".ttc")):
                continue

            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_file_path = Path(temp_dir) / filename
                    extract_arg = f"{att_id}:{temp_file_path}"

                    tool_result = await self._subprocess_port.execute(
                        ["mkvextract", "attachments", str(mkv_path), extract_arg],
                        timeout=30.0,
                    )
                    if not tool_result.success:
                        continue

                    font_bytes = await asyncio.to_thread(temp_file_path.read_bytes)
                    nameids = verify_font(font_bytes, filename)

                    if nameids and font_name_matches(query.requested_name, nameids):
                        primary_name = (
                            nameids.get(4) or nameids.get(1) or Path(filename).stem
                        )
                        duration_ms = (time.perf_counter() - start_time) * 1000.0

                        logger.info(
                            "MkvExtractHunter matched internal font name",
                            requested_name=query.requested_name,
                            matched_name=primary_name,
                            mkv_path=str(mkv_path),
                            attachment_id=att_id,
                        )

                        # Store the attachment metadata in nameids to be used if needed
                        nameids_meta = {
                            **nameids,
                            1000: str(att_id),
                            1001: filename,
                        }

                        payload = FontPayload(
                            font_name=primary_name,
                            font_data=font_bytes,
                            file_extension=Path(filename).suffix.lower(),
                            source=self.name,
                            nameids=nameids_meta,
                            metadata={
                                "mkv_path": str(mkv_path),
                                "attachment_id": str(att_id),
                            },
                        )

                        self._cache[normalized] = payload

                        asset = FontAsset(
                            name=primary_name,
                            file_path=mkv_path,
                            source="mkv_extract",
                            layer_found=self.priority,
                            cache_hit=False,
                            nameids=nameids_meta,
                            is_cacheable=True,
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
                    "Error checking attachment during search",
                    filename=filename,
                    error=str(e),
                )

        logger.debug("MkvExtract font miss", requested_name=query.requested_name)
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        normalized = normalize_font_name(result.query.requested_name)
        payload = self._cache.get(normalized)
        if not payload:
            raise ValueError("Download called without successful search first")
        return payload
