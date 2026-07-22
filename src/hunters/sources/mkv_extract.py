import asyncio
from collections import deque
import json
from pathlib import Path
import tempfile
import time
from typing import TypeAlias

import structlog

from src.errors import PipelineStoppedError
from src.hunters.sources._hunter_utils import (
    font_name_matches,
    normalize_font_name,
    verify_font,
)
from src.models.font import FontAsset, FontPayload, FontQuery, HunterResult
from src.ports.font_hunter import FontSearchScope
from src.ports.subprocess import SubprocessPort

logger = structlog.get_logger()

Attachment: TypeAlias = tuple[Path, int, str]
CacheKey: TypeAlias = tuple[str, str]
DirectoryEntry: TypeAlias = tuple[Path, bool, bool]


def _raise_if_stopped(stop_event: asyncio.Event | None) -> None:
    """Raise only from the event-loop thread when a run is stopped."""
    if stop_event is not None and stop_event.is_set():
        raise PipelineStoppedError("MKV font discovery stopped by user")


def _list_directory(directory: Path) -> list[DirectoryEntry]:
    """Return one deterministic directory listing for a bounded worker call."""
    entries = [(path, path.is_dir(), path.is_file()) for path in directory.iterdir()]
    return sorted(entries, key=lambda entry: (entry[0].name.casefold(), str(entry[0])))


def _is_hidden_child(path: Path, root: Path) -> bool:
    """Exclude hidden paths without allowing traversal outside the scoped root."""
    try:
        relative_path = path.relative_to(root)
    except ValueError:
        return True
    return any(part.startswith(".") for part in relative_path.parts)


class MkvExtractHunter:
    """Find embedded fonts within an immutable, per-run media discovery scope."""

    name: str = "MkvExtractHunter"
    priority: int = 1
    rate_limit: float = 0.0
    circuit_breaker_threshold: int = 3
    ping_url: str | None = None

    def __init__(
        self,
        subprocess_port: SubprocessPort,
        library_path: Path | None = None,
        *,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Create a legacy-root hunter or an initially unscoped factory hunter.

        ``library_path`` remains supported for callers that perform a full-library
        run directly. New pipeline runs use :meth:`for_run`, which returns a fresh
        instance rather than mutating this one.
        """
        self._subprocess_port = subprocess_port
        self._scope = FontSearchScope(library_path)
        self._stop_event = stop_event
        self._scanned = False
        self._attachments: list[Attachment] = []
        self._payload_cache: dict[CacheKey, FontPayload] = {}
        self._asset_cache: dict[CacheKey, FontAsset] = {}
        self._miss_cache: set[CacheKey] = set()
        self._scan_lock = asyncio.Lock()

    @property
    def scope(self) -> FontSearchScope:
        """Expose the immutable scope for diagnostics and focused tests."""
        return self._scope

    def for_run(
        self,
        discovery_root: Path | None,
        stop_event: asyncio.Event | None = None,
    ) -> "MkvExtractHunter":
        """Return a new hunter with isolated attachments and result caches."""
        return MkvExtractHunter(
            subprocess_port=self._subprocess_port,
            library_path=discovery_root,
            stop_event=stop_event,
        )

    def supports(self, query: FontQuery) -> bool:
        return True

    def _cache_key(self, requested_name: str) -> CacheKey:
        return (self._scope.identity, normalize_font_name(requested_name))

    async def _enumerate_mkvs(self) -> list[Path]:
        """Walk only this run's root through cancellable, bounded listings."""
        root = self._scope.discovery_root
        if root is None:
            return []

        directories: deque[Path] = deque([root])
        mkv_paths: list[Path] = []
        while directories:
            _raise_if_stopped(self._stop_event)
            directory = directories.popleft()
            try:
                children = await asyncio.to_thread(_list_directory, directory)
            except OSError as error:
                logger.warning(
                    "failed to list scoped font-discovery directory",
                    directory=str(directory),
                    error=str(error),
                )
                continue

            _raise_if_stopped(self._stop_event)
            for child, is_directory, is_file in children:
                _raise_if_stopped(self._stop_event)
                if _is_hidden_child(child, root):
                    continue
                if is_directory:
                    directories.append(child)
                elif is_file and child.suffix.lower() == ".mkv":
                    mkv_paths.append(child)

            await asyncio.sleep(0)
            _raise_if_stopped(self._stop_event)

        return mkv_paths

    async def _scan_library(self) -> None:
        """Index embedded-font attachments without leaking partial stopped state."""
        async with self._scan_lock:
            if self._scanned:
                return

            _raise_if_stopped(self._stop_event)
            discovered_attachments: list[Attachment] = []
            try:
                mkv_paths = await self._enumerate_mkvs()
                logger.info(
                    "scanning scoped MKV files for fonts",
                    discovery_root=(
                        str(self._scope.discovery_root)
                        if self._scope.discovery_root is not None
                        else None
                    ),
                    scope_identity=self._scope.identity,
                    mkv_count=len(mkv_paths),
                )

                for mkv_path in mkv_paths:
                    _raise_if_stopped(self._stop_event)
                    try:
                        result = await self._subprocess_port.execute(
                            ["mkvmerge", "-J", str(mkv_path)], timeout=30.0
                        )
                    except asyncio.CancelledError:
                        raise
                    except PipelineStoppedError:
                        raise
                    except Exception as error:
                        logger.debug(
                            "failed to scan attachments in MKV",
                            path=str(mkv_path),
                            error=str(error),
                        )
                        continue

                    _raise_if_stopped(self._stop_event)
                    if not result.success:
                        continue

                    try:
                        document = json.loads(result.stdout)
                    except json.JSONDecodeError:
                        logger.debug(
                            "mkvmerge attachment scan returned invalid JSON",
                            path=str(mkv_path),
                        )
                        continue
                    if not isinstance(document, dict):
                        continue
                    raw_attachments = document.get("attachments", [])
                    if not isinstance(raw_attachments, list):
                        continue

                    for attachment in raw_attachments:
                        _raise_if_stopped(self._stop_event)
                        if not isinstance(attachment, dict):
                            continue
                        filename = attachment.get("file_name", "")
                        content_type = attachment.get("content_type", "")
                        attachment_id = attachment.get("id")
                        if (
                            not isinstance(filename, str)
                            or not isinstance(content_type, str)
                            or not isinstance(attachment_id, int)
                        ):
                            continue
                        if filename.lower().endswith((".ttf", ".otf", ".ttc")) or (
                            "font" in content_type.lower()
                        ):
                            discovered_attachments.append(
                                (mkv_path, attachment_id, filename)
                            )
            except asyncio.CancelledError:
                self._attachments.clear()
                self._scanned = False
                raise
            except PipelineStoppedError:
                self._attachments.clear()
                self._scanned = False
                raise

            self._attachments = discovered_attachments
            self._scanned = True

    def _result_for(
        self,
        query: FontQuery,
        asset: FontAsset,
        duration_ms: float,
    ) -> HunterResult:
        """Bind a cached asset to the current query instead of a stale one."""
        return HunterResult(
            query=query,
            font_asset=asset,
            success=True,
            hunter_name=self.name,
            duration_ms=duration_ms,
            attempts=1,
        )

    async def search(self, query: FontQuery) -> list[HunterResult]:
        """Search only the immutable discovery scope configured for this instance."""
        _raise_if_stopped(self._stop_event)
        logger.debug(
            "MkvExtractHunter search start",
            requested=query.requested_name,
            scope_identity=self._scope.identity,
        )

        cache_key = self._cache_key(query.requested_name)
        cached_asset = self._asset_cache.get(cache_key)
        if cached_asset is not None:
            logger.debug(
                "MkvExtractHunter result cache hit",
                requested=query.requested_name,
                scope_identity=self._scope.identity,
            )
            return [self._result_for(query, cached_asset, duration_ms=0.0)]
        if cache_key in self._miss_cache:
            logger.debug(
                "MkvExtractHunter negative cache hit",
                requested=query.requested_name,
                scope_identity=self._scope.identity,
            )
            return []

        await self._scan_library()
        _raise_if_stopped(self._stop_event)
        start_time = time.perf_counter()

        for mkv_path, attachment_id, filename in self._attachments:
            _raise_if_stopped(self._stop_event)
            if not filename.lower().endswith((".ttf", ".otf", ".ttc")):
                continue

            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_file_path = Path(temp_dir) / filename
                    extract_arg = f"{attachment_id}:{temp_file_path}"
                    tool_result = await self._subprocess_port.execute(
                        ["mkvextract", "attachments", str(mkv_path), extract_arg],
                        timeout=30.0,
                    )
                    _raise_if_stopped(self._stop_event)
                    if not tool_result.success:
                        continue

                    font_bytes = await asyncio.to_thread(temp_file_path.read_bytes)
                    _raise_if_stopped(self._stop_event)
                    nameids = verify_font(font_bytes, filename)
                    if not nameids or not font_name_matches(
                        query.requested_name, nameids
                    ):
                        continue

                    primary_name = (
                        nameids.get(4) or nameids.get(1) or Path(filename).stem
                    )
                    nameids_meta = {
                        **nameids,
                        1000: str(attachment_id),
                        1001: filename,
                        1002: self._scope.identity,
                        1003: str(mkv_path),
                    }
                    payload = FontPayload(
                        font_name=primary_name,
                        font_data=font_bytes,
                        file_extension=Path(filename).suffix.lower(),
                        source=self.name,
                        nameids=nameids_meta,
                        metadata={
                            "mkv_path": str(mkv_path),
                            "attachment_id": str(attachment_id),
                            "discovery_root": str(self._scope.discovery_root),
                            "scope_identity": self._scope.identity,
                        },
                    )
                    asset = FontAsset(
                        name=primary_name,
                        file_path=mkv_path,
                        source="mkv_extract",
                        layer_found=self.priority,
                        cache_hit=False,
                        nameids=nameids_meta,
                        is_cacheable=True,
                    )
                    self._payload_cache[cache_key] = payload
                    self._asset_cache[cache_key] = asset
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    logger.info(
                        "MkvExtractHunter matched internal font name",
                        requested_name=query.requested_name,
                        matched_name=primary_name,
                        mkv_path=str(mkv_path),
                        attachment_id=attachment_id,
                        scope_identity=self._scope.identity,
                    )
                    return [self._result_for(query, asset, duration_ms)]
            except asyncio.CancelledError:
                raise
            except PipelineStoppedError:
                raise
            except Exception as error:
                logger.debug(
                    "error checking attachment during search",
                    filename=filename,
                    error=str(error),
                )

        _raise_if_stopped(self._stop_event)
        self._miss_cache.add(cache_key)
        logger.debug(
            "MkvExtract font miss",
            requested=query.requested_name,
            scope_identity=self._scope.identity,
        )
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        _raise_if_stopped(self._stop_event)
        cache_key = self._cache_key(result.query.requested_name)
        payload = self._payload_cache.get(cache_key)
        if payload is None:
            raise ValueError("Download called without successful search in this scope")
        return payload
