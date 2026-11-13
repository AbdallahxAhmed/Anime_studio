"""Application facade the desktop UI talks to (one method per user action)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from src.config import AppConfig
from src.core.library_scanner import get_info
from src.errors import PipelineStoppedError
from src.models.pipeline import PipelineConfig
from src.models.report import PipelineReport
from src.models.subtitle import SubtitleSource
from src.sidecar.container import Services, config_path
from src.sidecar.rpc import INVALID_PARAMS, RpcError

Notify = Callable[[dict[str, Any]], None]

VERSION = "3.0.0-dev"


def _path(params: dict[str, Any], key: str) -> Path:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise RpcError(f"'{key}' must be a non-empty path", INVALID_PARAMS)
    return Path(value).expanduser()


def _visible(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    return not any(part.startswith(".") for part in parts)


def _mkvs(folder: Path) -> list[Path]:
    return sorted(
        (p for p in folder.rglob("*.mkv") if p.is_file() and _visible(p, folder)),
        key=lambda p: p.name.casefold(),
    )


def _list_shows(root: Path) -> list[dict[str, Any]]:
    shows: list[dict[str, Any]] = []
    if not root.is_dir():
        return shows
    for show in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if not show.is_dir() or show.name.startswith("."):
            continue
        seasons: list[dict[str, Any]] = []
        for child in sorted(show.iterdir(), key=lambda p: p.name.casefold()):
            if child.is_dir() and not child.name.startswith("."):
                count = len(_mkvs(child))
                if count:
                    seasons.append(
                        {"name": child.name, "path": str(child), "episodes": count}
                    )
        direct = sum(1 for p in show.glob("*.mkv") if p.is_file())
        total = direct + sum(int(s["episodes"]) for s in seasons)
        if total:
            shows.append(
                {
                    "name": show.name,
                    "path": str(show),
                    "episodes": total,
                    "seasons": seasons,
                }
            )
    return shows


class AppService:
    def __init__(self, services: Services, notify: Notify) -> None:
        self.s = services
        self.notify = notify
        self._run_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    # -- app and config -------------------------------------------------

    @property
    def config(self) -> AppConfig:
        return self.s.config

    def _config_view(self) -> dict[str, Any]:
        sub = self.config.subtitle
        return {
            "library_path": str(self.config.library_path or ""),
            "preferred_language": sub.preferred_language,
            "strict_language": sub.strict_language,
            "set_default": sub.set_default,
            "sync_by_default": sub.sync_by_default,
            "proxy": self.config.proxy or "",
            "trash_max_age_days": self.config.trash_max_age_days,
        }

    async def info(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": VERSION,
            "platform": self.s.platform_name,
            "data_dir": str(self.s.data_dir),
            "tools": [asdict(t) for t in self.s.tools],
            "missing_required_tools": self.s.missing_required_tools,
            "config": self._config_view(),
        }

    async def update_config(self, params: dict[str, Any]) -> dict[str, Any]:
        sub = self.config.subtitle
        if "library_path" in params:
            value = params["library_path"]
            self.config.library_path = Path(value).expanduser() if value else None
        for key in ("preferred_language",):
            if key in params:
                setattr(sub, key, str(params[key]))
        for key in ("strict_language", "set_default", "sync_by_default"):
            if key in params:
                setattr(sub, key, bool(params[key]))
        if "proxy" in params:
            self.config.proxy = str(params["proxy"]) or None
        await asyncio.to_thread(self.config.save_to_toml, config_path())
        return self._config_view()

    # -- library --------------------------------------------------------

    async def shows(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        root = _path(params, "root") if params.get("root") else self.config.library_path
        if root is None:
            return []
        return await asyncio.to_thread(_list_shows, Path(root))

    async def episodes(self, params: dict[str, Any]) -> dict[str, Any]:
        folder = _path(params, "path")
        if not folder.is_dir():
            raise RpcError(f"Folder not found: {folder}")
        scan = await self.s.scanner.scan_folder(folder)
        matched = {r.episode_path: r for r in scan.episodes}
        language = self.config.subtitle.preferred_language
        rows: list[dict[str, Any]] = []
        for mkv in await asyncio.to_thread(_mkvs, folder):
            info = get_info(mkv.name)
            row: dict[str, Any] = {
                "path": str(mkv),
                "name": mkv.name,
                "number": info[1] if info else None,
                "subtitle": None,
                "status": "no_subtitle",
            }
            result = matched.get(mkv.resolve())
            if result is not None and result.subtitle_source == SubtitleSource.EXTERNAL:
                row["subtitle"] = {
                    "kind": "external",
                    "path": str(result.subtitle_path),
                    "name": Path(str(result.subtitle_path)).name,
                }
                row["status"] = "ready"
            elif result is not None and result.embedded_sub_info is not None:
                tracks = result.embedded_sub_info.tracks
                wanted = [t for t in tracks if t.language.lower() == language.lower()]
                row["subtitle"] = {
                    "kind": "embedded",
                    "tracks": [
                        {
                            "id": t.track_id,
                            "language": t.language,
                            "default": t.is_default,
                        }
                        for t in tracks
                    ],
                }
                row["status"] = "ready" if wanted else "other_language"
            rows.append(row)
        return {"path": str(folder), "name": folder.name, "episodes": rows}

    # -- runs -----------------------------------------------------------

    async def start_run(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._run_task is not None and not self._run_task.done():
            raise RpcError("A run is already in progress")
        if self.s.missing_required_tools and not params.get("dry_run"):
            raise RpcError(
                "Missing required tools: " + ", ".join(self.s.missing_required_tools)
            )
        show = _path(params, "show_path")
        episodes = params.get("episodes")
        if not isinstance(episodes, list) or not episodes:
            raise RpcError("'episodes' must be a non-empty list", INVALID_PARAMS)
        library = self.config.library_path or show.parent
        try:
            # A season folder belongs to the show folder right under the library.
            title = show.resolve().relative_to(Path(library).resolve()).parts[0]
        except (ValueError, IndexError):
            title = show.name
        pipeline_config = PipelineConfig(
            library_path=library,
            discovery_root=show,
            dry_run=bool(params.get("dry_run", False)),
            sync_enabled=bool(params.get("sync", self.config.subtitle.sync_by_default)),
            anime_title=title,
            selected_paths=frozenset(Path(str(p)).resolve() for p in episodes),
        )
        run_id = str(uuid.uuid4())
        self._stop_event = asyncio.Event()
        self._run_task = asyncio.create_task(
            self._run(run_id, pipeline_config, self._stop_event)
        )
        return {"run_id": run_id}

    async def _run(
        self, run_id: str, config: PipelineConfig, stop_event: asyncio.Event
    ) -> None:
        self.notify({"type": "run.started", "run_id": run_id})
        try:
            report = await self.s.runner.run(
                config,
                stop_event=stop_event,
                checkpoint_manager=self.s.checkpoints,
                undo_service=self.s.undo,
            )
        except PipelineStoppedError:
            self.notify({"type": "run.stopped", "run_id": run_id})
            return
        except asyncio.CancelledError:
            self.notify({"type": "run.stopped", "run_id": run_id})
            raise
        except Exception as error:
            self.notify({"type": "run.failed", "run_id": run_id, "error": str(error)})
            return
        self.notify(
            {"type": "run.finished", "run_id": run_id, **self._summarize(report)}
        )

    @staticmethod
    def _summarize(report: PipelineReport) -> dict[str, Any]:
        return {
            "duration_ms": report.duration_ms,
            "episodes": [
                {
                    "path": str(e.episode_path),
                    "status": e.status.value,
                    "fonts_attached": e.mux_result.fonts_attached
                    if e.mux_result
                    else 0,
                    "missing_fonts": list(e.missing_fonts),
                    "messages": list(e.applied_rules),
                }
                for e in report.episodes
            ],
        }

    async def stop_run(self, _params: dict[str, Any]) -> dict[str, Any]:
        if self._stop_event is None or self._run_task is None or self._run_task.done():
            return {"stopping": False}
        self._stop_event.set()
        return {"stopping": True}

    async def shutdown(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._run_task is not None:
            await asyncio.gather(self._run_task, return_exceptions=True)

    # -- history / undo ---------------------------------------------------

    async def history(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        runs = await self.s.undo.list_runs()
        return [
            {
                "run_id": run.run_id,
                "timestamp": run.timestamp,
                "library_path": str(run.library_path),
                "shows": run.show_names,
                "episodes": [
                    {
                        "path": str(ep.episode_path),
                        "show": ep.show_name,
                        "status": ep.status,
                        "restorable": bool(ep.trash_receipt_path),
                    }
                    for ep in run.episodes_processed
                ],
            }
            for run in runs
        ]

    async def undo(self, params: dict[str, Any]) -> dict[str, int]:
        run_id = params.get("run_id")
        runs = await self.s.undo.list_runs()
        manifest = next((r for r in runs if r.run_id == run_id), None)
        if manifest is None:
            raise RpcError(f"Run not found: {run_id}")
        wanted = params.get("episodes")
        totals = {"restored": 0, "failed": 0, "missing": 0}
        targets = (
            [str(p) for p in wanted]
            if isinstance(wanted, list) and wanted
            else [
                str(ep.episode_path)
                for ep in manifest.episodes_processed
                if ep.trash_receipt_path
            ]
        )
        for path in targets:
            # Re-read: each undo rewrites the manifest.
            current = next(
                r for r in await self.s.undo.list_runs() if r.run_id == run_id
            )
            result = await self.s.undo.undo_episode(current, path)
            totals["restored"] += result.restored
            totals["failed"] += result.failed + result.conflicts
            totals["missing"] += result.missing
        return totals

    async def import_fonts(self, params: dict[str, Any]) -> dict[str, int]:
        raw = params.get("paths")
        if not isinstance(raw, list):
            raise RpcError("'paths' must be a list", INVALID_PARAMS)
        files = [Path(str(p)) for p in raw]
        result = await self.s.font_ingestion.ingest_files(files)
        return {
            "added": result.success_count,
            "skipped": result.skipped_count,
            "failed": result.failed_count,
        }

    def handlers(self) -> dict[str, Callable[[dict[str, Any]], Any]]:
        return {
            "app.info": self.info,
            "config.update": self.update_config,
            "library.shows": self.shows,
            "library.episodes": self.episodes,
            "run.start": self.start_run,
            "run.stop": self.stop_run,
            "history.list": self.history,
            "history.undo": self.undo,
            "fonts.import": self.import_fonts,
        }
