import asyncio
from collections import deque
from datetime import datetime, timezone
from os.path import normcase
import time
from typing import Any, Literal
from pathlib import Path
import shutil
import structlog

from src.models.pipeline import LibraryScanResult, EpisodeContext, PipelineConfig
from src.models.report import EpisodeStatus, EpisodeReport, PipelineReport
from src.models.subtitle import SubtitleFile, SubtitleSource, SyncResult
from src.models.mux import MuxResult
from src.core.subtitle_repair import repair_ass, extract_fonts
from src.core.font_resolver import FontResolver
from src.core.font_ingestion import FontIngestionService
from src.core.mux_planner import plan_mux
from src.core.report_writer import render_report, render_incremental_section
from src.core.library_scanner import LibraryScanner
from src.ports.subprocess import SubprocessPort
from src.ports.filesystem import FilesystemPort
from src.adapters.dependency_checker import ToolRegistry
from src.config import AppConfig
from src.errors import FontMatchError, PipelineStoppedError

logger = structlog.get_logger()


def _raise_if_stopped(stop_event: asyncio.Event | None) -> None:
    """Stop a pipeline run without representing user intent as a failure."""
    if stop_event is not None and stop_event.is_set():
        raise PipelineStoppedError("Pipeline stopped by user")


def _is_ancestor(ancestor: Path, descendant: Path) -> bool:
    try:
        descendant.relative_to(ancestor)
        return True
    except ValueError:
        return False


def _normalized_path_key(path: Path) -> str:
    """Return a resolved, platform-normalized key for exact path identity."""
    return normcase(str(Path(path).expanduser().resolve()))


def _list_directory_entries(directory: Path) -> tuple[tuple[Path, bool, bool], ...]:
    """List one directory without reading cancellation state in a worker."""
    entries: list[tuple[Path, bool, bool]] = []
    for child in sorted(directory.iterdir(), key=lambda path: path.name.casefold()):
        try:
            entries.append((child, child.is_dir(), child.is_file()))
        except OSError:
            continue
    return tuple(entries)


async def _enumerate_mkvs(
    discovery_root: Path, stop_event: asyncio.Event | None
) -> list[Path]:
    """Return MKVs through bounded, event-loop-cooperative traversal."""
    pending_directories: deque[Path] = deque([discovery_root])
    mkv_paths: list[Path] = []

    while pending_directories:
        _raise_if_stopped(stop_event)
        directory = pending_directories.popleft()
        try:
            entries = await asyncio.to_thread(_list_directory_entries, directory)
        except OSError as error:
            logger.warning(
                "failed to list directory during skipped-MKV enumeration",
                directory=str(directory),
                error=str(error),
            )
            continue
        _raise_if_stopped(stop_event)

        for path, is_directory, is_file in entries:
            _raise_if_stopped(stop_event)
            if is_directory:
                pending_directories.append(path)
            elif is_file and path.suffix.lower() == ".mkv":
                mkv_paths.append(path)

        # This is a cooperative event-loop checkpoint, not a timing delay.
        await asyncio.sleep(0)
        _raise_if_stopped(stop_event)

    return sorted(mkv_paths, key=lambda path: (path.name.casefold(), str(path)))


async def _filter_selected_scans(
    scan_results: list[LibraryScanResult],
    selected_keys: set[str],
    stop_event: asyncio.Event | None,
) -> list[LibraryScanResult]:
    """Apply exact full-path selection without starving the event loop."""
    selected: list[LibraryScanResult] = []
    for index, scan in enumerate(scan_results, start=1):
        _raise_if_stopped(stop_event)
        if _normalized_path_key(scan.episode_path) in selected_keys:
            selected.append(scan)
        if index % 32 == 0:
            await asyncio.sleep(0)
            _raise_if_stopped(stop_event)
    return selected


class PipelineRunner:
    def __init__(
        self,
        font_resolver: FontResolver,
        subprocess_adapter: SubprocessPort,
        filesystem: FilesystemPort,
        tool_registry: ToolRegistry,
        config: AppConfig,
        font_ingestion_service: FontIngestionService,
        disk_semaphore: asyncio.Semaphore,
        library_scanner: LibraryScanner,
    ) -> None:
        self.font_resolver = font_resolver
        self.subprocess_adapter = subprocess_adapter
        self.filesystem = filesystem
        self.tool_registry = tool_registry
        self.config = config
        self.font_ingestion_service = font_ingestion_service
        self.disk_semaphore = disk_semaphore
        self.library_scanner = library_scanner
        self._analysis_lock = asyncio.Lock()

    async def run(
        self,
        pipeline_config: PipelineConfig,
        stop_event: asyncio.Event | None = None,
        checkpoint_manager: Any | None = None,
        undo_service: Any | None = None,
    ) -> PipelineReport:
        """Run the full library pipeline: scan, repair, resolve fonts, timing sync, plan mux, dispatch mux, trash, report."""
        start_time = time.perf_counter()
        run_timestamp = datetime.now(timezone.utc)
        effective_discovery_root = (
            Path(
                pipeline_config.discovery_root
                if pipeline_config.discovery_root is not None
                else pipeline_config.library_path
            )
            .expanduser()
            .resolve()
        )
        run_font_resolver = self.font_resolver.for_run(
            effective_discovery_root, stop_event
        )

        # 1. Scan Library
        _raise_if_stopped(stop_event)
        logger.info(
            "Library scan started",
            stage="scan",
            progress_current=None,
            progress_total=None,
        )
        if stop_event is None:
            scan_output = await self.library_scanner.scan(effective_discovery_root)
        else:
            scan_output = await self.library_scanner.scan(
                effective_discovery_root, stop_event=stop_event
            )
        _raise_if_stopped(stop_event)
        scan_results = scan_output.episodes

        completed_from_checkpoint = set()
        if checkpoint_manager:
            _raise_if_stopped(stop_event)
            checkpoint = await checkpoint_manager.load()
            _raise_if_stopped(stop_event)
            if (
                checkpoint
                and Path(checkpoint.library_path).resolve()
                == Path(pipeline_config.library_path).resolve()
            ):
                completed_from_checkpoint = set(checkpoint.completed_episodes)
                logger.info(
                    f"Resuming pipeline, skipping {len(completed_from_checkpoint)} completed episodes"
                )

        if completed_from_checkpoint:
            scan_results = [
                ep
                for ep in scan_results
                if str(ep.episode_path) not in completed_from_checkpoint
            ]

        if pipeline_config.selected_paths is not None:
            _raise_if_stopped(stop_event)
            selected_keys = {
                _normalized_path_key(path) for path in pipeline_config.selected_paths
            }
            original_count = len(scan_results)
            scan_results = await _filter_selected_scans(
                scan_results, selected_keys, stop_event
            )
            _raise_if_stopped(stop_event)
            logger.info(
                "Filtered episodes by selected paths",
                selected_count=len(scan_results),
                total_count=original_count,
                selected_paths_count=len(selected_keys),
            )

        _raise_if_stopped(stop_event)
        font_dirs = scan_output.font_directories
        logger.info(
            f"Library scan complete. Found {len(scan_results)} episodes.",
            stage="scan",
            progress_current=None,
            progress_total=len(scan_results),
        )

        # Pre-pipeline font ingestion step
        _raise_if_stopped(stop_event)
        if font_dirs:
            logger.info(
                "Auto-discovered font directories, starting ingestion",
                directories=font_dirs,
            )
            await self.font_ingestion_service.ingest_directories(
                font_dirs, source="auto_discovery"
            )
        _raise_if_stopped(stop_event)

        # Resolve anime_title
        anime_title = pipeline_config.anime_title
        if not anime_title:
            if scan_results:
                anime_title = scan_results[0].anime_title
            else:
                anime_title = effective_discovery_root.name or "Unknown"

        if not scan_results:
            logger.info("no episodes found during scan")
            report = PipelineReport(
                run_timestamp=run_timestamp,
                duration_ms=0.0,
                anime_title=anime_title,
                episodes=[],
                total_fonts_found=0,
                genuine_misses=[],
            )
            # Write empty report
            _raise_if_stopped(stop_event)
            report_md = render_report(report)
            report_path = Path(pipeline_config.library_path) / "_AnimeStudio_Report.md"
            _raise_if_stopped(stop_event)
            await self.filesystem.write_file_atomic(report_path, report_md)
            _raise_if_stopped(stop_event)
            return report

        # Find skipped episodes (MKVs without matching ASS)
        _raise_if_stopped(stop_event)
        all_mkvs = await _enumerate_mkvs(effective_discovery_root, stop_event)
        _raise_if_stopped(stop_event)
        scanned_mkv_paths = {Path(s.episode_path).resolve() for s in scan_results}
        skipped_reports = []
        for mkv in all_mkvs:
            _raise_if_stopped(stop_event)
            if mkv.resolve() not in scanned_mkv_paths:
                skipped_reports.append(
                    EpisodeReport(
                        episode_path=mkv.resolve(),
                        status=EpisodeStatus.SKIPPED,
                    )
                )

        # 2. Sequential Analysis Phase
        # Filter: only process episodes with external subtitles.
        # Embedded-only episodes are logged and skipped (no external sub to process).
        external_scans = []
        embedded_only_reports = []
        for scan in scan_results:
            _raise_if_stopped(stop_event)
            if scan.subtitle_source == SubtitleSource.EMBEDDED:
                logger.info(
                    "skipping embedded-only episode (no external subtitle to process)",
                    episode=scan.episode_path.name,
                    embedded_tracks=scan.embedded_sub_info.track_count
                    if scan.embedded_sub_info
                    else 0,
                )
                embedded_only_reports.append(
                    EpisodeReport(
                        episode_path=scan.episode_path,
                        status=EpisodeStatus.SKIPPED,
                    )
                )
            else:
                external_scans.append(scan)

        episode_contexts = []
        for scan in external_scans:
            _raise_if_stopped(stop_event)
            ctx = await self._analyze_episode(
                scan,
                anime_title,
                pipeline_config,
                run_timestamp,
                stop_event=stop_event,
                font_resolver=run_font_resolver,
            )
            _raise_if_stopped(stop_event)
            episode_contexts.append(ctx)
            if checkpoint_manager:
                _raise_if_stopped(stop_event)
                from src.models.run_manifest import PipelineCheckpoint

                completed_list = list(completed_from_checkpoint) + [
                    str(c.scan_result.episode_path) for c in episode_contexts
                ]
                checkpoint = PipelineCheckpoint(
                    library_path=str(pipeline_config.library_path),
                    completed_episodes=tuple(completed_list),
                    timestamp=run_timestamp.isoformat(),
                    selected_paths=tuple(
                        str(sp) for sp in (pipeline_config.selected_paths or ())
                    ),
                )
                await checkpoint_manager.save(checkpoint)
                _raise_if_stopped(stop_event)

        # 3. Concurrent Mux Concurrency Semaphore
        mux_semaphore = self.disk_semaphore
        completed_mux_count = 0
        mux_counter_lock = asyncio.Lock()
        total_episodes = len(episode_contexts)

        # Helper to run mux and post-process
        async def _mux_and_post_process(ctx: EpisodeContext) -> EpisodeContext:
            nonlocal completed_mux_count
            _raise_if_stopped(stop_event)
            if ctx.status == EpisodeStatus.FAILED:
                # Still increment progress for already failed ones if we are counting them,
                # but they are excluded from the concurrent mux list.
                # Actually, only non-failed ones make it to muxing. But to be safe:
                return ctx

            if not ctx.mux_job:
                return ctx.model_copy(
                    update={
                        "status": EpisodeStatus.FAILED,
                        "errors": ctx.errors + ["MuxJob was not planned."],
                    }
                )

            async with mux_semaphore:
                _raise_if_stopped(stop_event)
                logger.info(
                    f"Muxing episode: {ctx.scan_result.episode_path.name}",
                    stage="mux",
                    progress_current=completed_mux_count + 1,
                    progress_total=total_episodes,
                )
                try:
                    from src.adapters.mkvmerge import MkvmergeAdapter

                    mkvmerge_adapter = MkvmergeAdapter(self.subprocess_adapter)

                    if pipeline_config.dry_run:
                        # Simulated success
                        mux_res = MuxResult(
                            success=True,
                            output_path=ctx.mux_job.output_path,
                            duration_ms=0.0,
                            fonts_attached=len(ctx.mux_job.fonts),
                            warnings=[],
                        )
                    else:
                        mux_res = await mkvmerge_adapter.mux(
                            ctx.mux_job, timeout=float(self.config.mux_timeout_s)
                        )

                    _raise_if_stopped(stop_event)
                    if not mux_res.success:
                        return ctx.model_copy(
                            update={
                                "mux_result": mux_res,
                                "status": EpisodeStatus.FAILED,
                                "errors": ctx.errors + ["mkvmerge muxing failed."],
                            }
                        )

                    # Plan trash
                    trash_receipts = []
                    sub_file = SubtitleFile(
                        path=ctx.scan_result.subtitle_path,
                        encoding_detected="utf-8",
                        encoding_source="repair",
                        line_ending="\n",
                        fonts_required=[q.requested_name for q in ctx.font_queries],
                    )
                    sub_trash = sub_file.plan_trash_disposal(
                        run_timestamp, self.config.trash_max_age_days
                    )
                    trash_receipts.append(sub_trash)

                    mkv_trash = ctx.mux_job.plan_trash_disposal(
                        run_timestamp, self.config.trash_max_age_days
                    )
                    trash_receipts.append(mkv_trash)

                    if not pipeline_config.dry_run:
                        # Perform trash moves
                        sub_path = ctx.scan_result.subtitle_path
                        assert sub_path is not None
                        _raise_if_stopped(stop_event)
                        await self.filesystem.move_to_trash(sub_path, sub_trash)
                        _raise_if_stopped(stop_event)
                        await self.filesystem.move_to_trash(
                            ctx.scan_result.episode_path, mkv_trash
                        )
                        _raise_if_stopped(stop_event)
                        # Atomic replace original MKV with temporary muxed file
                        assert ctx.mux_job is not None
                        await self.filesystem.replace_file(
                            ctx.mux_job.output_path, ctx.scan_result.episode_path
                        )
                        _raise_if_stopped(stop_event)
                        # Cleanup temp ASS file if exists
                        temp_sub_path = sub_path.with_name(f"{sub_path.stem}.tmp.ass")
                        if temp_sub_path.exists():
                            try:
                                temp_sub_path.unlink()
                            except Exception:
                                pass

                    # Determine final status
                    has_missing_fonts = len(ctx.missing_fonts) > 0
                    has_sync_fail = (
                        ctx.sync_result is not None and not ctx.sync_result.success
                    )

                    if has_missing_fonts or has_sync_fail:
                        final_status = EpisodeStatus.PARTIAL
                    else:
                        final_status = EpisodeStatus.COMPLETE

                    res_ctx = ctx.model_copy(
                        update={
                            "mux_result": mux_res,
                            "trash_receipts": trash_receipts,
                            "status": final_status,
                        }
                    )

                    async with mux_counter_lock:
                        completed_mux_count += 1
                        current_idx = completed_mux_count
                    logger.info(
                        f"Mux completed: {ctx.scan_result.episode_path.name}",
                        stage="mux",
                        progress_current=current_idx,
                        progress_total=total_episodes,
                    )
                    return res_ctx

                except (PipelineStoppedError, asyncio.CancelledError):
                    raise
                except Exception as e:
                    logger.error(
                        "muxing or post-processing failed",
                        episode=ctx.scan_result.episode_path.name,
                        error=str(e),
                    )
                    async with mux_counter_lock:
                        completed_mux_count += 1
                        current_idx = completed_mux_count
                    logger.info(
                        f"Mux failed: {ctx.scan_result.episode_path.name}",
                        stage="mux",
                        progress_current=current_idx,
                        progress_total=total_episodes,
                    )
                    return ctx.model_copy(
                        update={
                            "status": EpisodeStatus.FAILED,
                            "errors": ctx.errors + [f"Mux post-processing error: {e}"],
                        }
                    )

        _raise_if_stopped(stop_event)
        # Keep only a bounded number of owned mux tasks.  The shared disk
        # semaphore remains the cross-run I/O guard; this scheduler also avoids
        # creating one task per episode for a large library.
        max_unfinished_mux_tasks = max(1, self.config.max_concurrent_disk_io)
        pending_mux_tasks: set[asyncio.Future[EpisodeContext]] = set()
        remaining_contexts = iter(episode_contexts)
        final_contexts: list[EpisodeContext] = []

        async def _drain_owned_mux_tasks(*, cancel: bool) -> None:
            if cancel:
                for task in pending_mux_tasks:
                    if not task.done():
                        task.cancel()
            if pending_mux_tasks:
                await asyncio.gather(*pending_mux_tasks, return_exceptions=True)

        def _schedule_next_mux() -> bool:
            _raise_if_stopped(stop_event)
            try:
                context = next(remaining_contexts)
            except StopIteration:
                return False
            pending_mux_tasks.add(asyncio.create_task(_mux_and_post_process(context)))
            return True

        try:
            while (
                len(pending_mux_tasks) < max_unfinished_mux_tasks
                and _schedule_next_mux()
            ):
                pass

            while pending_mux_tasks:
                done, pending_mux_tasks = await asyncio.wait(
                    pending_mux_tasks, return_when=asyncio.FIRST_COMPLETED
                )
                stopped = stop_event is not None and stop_event.is_set()
                native_cancelled = False
                for task in done:
                    try:
                        final_contexts.append(task.result())
                    except asyncio.CancelledError:
                        # Read every completed task before escalating native
                        # cancellation so a sibling exception is never lost.
                        native_cancelled = True
                    except PipelineStoppedError:
                        stopped = True

                if native_cancelled:
                    raise asyncio.CancelledError

                if stopped:
                    # Do not cancel user-owned binary work; let started muxes
                    # finish, consume their outcomes, and discard them.
                    await _drain_owned_mux_tasks(cancel=False)
                    raise PipelineStoppedError("Pipeline stopped by user")

                while (
                    len(pending_mux_tasks) < max_unfinished_mux_tasks
                    and _schedule_next_mux()
                ):
                    pass
        except asyncio.CancelledError:
            await _drain_owned_mux_tasks(cancel=True)
            raise
        except PipelineStoppedError:
            await _drain_owned_mux_tasks(cancel=False)
            raise
        except Exception:
            await _drain_owned_mux_tasks(cancel=True)
            raise
        _raise_if_stopped(stop_event)

        # Build reports list
        episode_reports = []
        for ctx in final_contexts:
            episode_reports.append(
                EpisodeReport(
                    episode_path=ctx.scan_result.episode_path,
                    status=ctx.status,
                    subtitle_result=ctx.sync_result,
                    mux_result=ctx.mux_result,
                    missing_fonts=ctx.missing_fonts,
                    applied_rules=ctx.errors,  # Store errors/applied rules context
                )
            )

        # Append skipped ones (MKVs without any subs + embedded-only)
        episode_reports.extend(skipped_reports)
        episode_reports.extend(embedded_only_reports)

        # Calculate overall font totals and misses
        total_fonts_found = sum(len(ctx.resolved_fonts) for ctx in final_contexts)
        genuine_misses_set = set()
        for ctx in final_contexts:
            genuine_misses_set.update(ctx.missing_fonts)

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        report = PipelineReport(
            run_timestamp=run_timestamp,
            duration_ms=duration_ms,
            anime_title=anime_title,
            episodes=episode_reports,
            total_fonts_found=total_fonts_found,
            genuine_misses=sorted(list(genuine_misses_set)),
        )

        # Write or append report
        _raise_if_stopped(stop_event)
        report_path = Path(pipeline_config.library_path) / "_AnimeStudio_Report.md"

        # Decide full vs incremental write
        # "T042 [US4] Implement full-vs-incremental write logic in PipelineRunner — detect if existing report, full run -> overwrite, partial run -> append via incremental section"
        # Wait, if all episodes in scan_results are processed, is it a full run?
        # A partial run would be if we only run a subset or if the user asks, but in our case, if the file exists and we want to append or overwrite.
        # Let's say if we detect an existing report:
        # If it exists, does it mean we append or overwrite?
        # Let's check if there is an option in PipelineConfig for partial/incremental.
        # Usually, if we do a new full run, we overwrite. If it's a partial scan or append is requested:
        # Wait, let's look at `specs/004-pipeline/spec.md` SC-007:
        # "Given the report already exists from a previous full run, When a new full run completes, Then the old report is overwritten with the new canonical report."
        # "Given a partial/incremental run, When the report is generated, Then it appends to the existing report with a clearly delimited section header rather than overwriting."
        # Wait! How does the runner know if it's a partial/incremental run?
        # We can look at `pipeline_config` to see if there is any parameter, or we can check if `pipeline_config.anime_title` is set, or if we have fewer episodes than the total MKVs?
        # Yes! If the number of processed episodes (`len(scan_results)`) is less than the total MKVs in the directory (`len(all_mkvs)`), then it's a partial/incremental run!
        # That is an extremely intelligent and deterministic heuristic!
        # Let's check:
        # - If `report_path.exists()` is True, AND `len(scan_results) < len(all_mkvs)`:
        #   - Read the existing report content.
        #   - Append `render_incremental_section(report)` to it!
        # - Else:
        #   - Write/overwrite with `render_report(report)`.
        # This is absolutely amazing! It perfectly covers the requirement with zero configuration overhead!

        if report_path.is_file() and len(scan_results) < len(all_mkvs):
            # Read existing report
            def _read_report() -> str:
                with open(report_path, "r", encoding="utf-8") as f:
                    return f.read()

            try:
                existing_content = await asyncio.to_thread(_read_report)
                _raise_if_stopped(stop_event)
                incremental_section = render_incremental_section(report)
                new_content = f"{existing_content}\n{incremental_section}"
                _raise_if_stopped(stop_event)
                await self.filesystem.write_file_atomic(report_path, new_content)
                _raise_if_stopped(stop_event)
            except PipelineStoppedError:
                raise
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    "failed to append to existing report, overwriting instead",
                    error=str(e),
                )
                report_md = render_report(report)
                _raise_if_stopped(stop_event)
                await self.filesystem.write_file_atomic(report_path, report_md)
                _raise_if_stopped(stop_event)
        else:
            report_md = render_report(report)
            _raise_if_stopped(stop_event)
            await self.filesystem.write_file_atomic(report_path, report_md)
            _raise_if_stopped(stop_event)

        # Write RunManifest on completion (normal or stopped)
        _raise_if_stopped(stop_event)
        if undo_service and final_contexts:
            from src.models.run_manifest import RunManifest, EpisodeProcessed

            manifest_episodes = []
            for ctx in final_contexts:
                # Map EpisodeStatus to "success", "skipped", "failed"
                status: Literal["success", "skipped", "failed"]
                if ctx.status in (EpisodeStatus.COMPLETE, EpisodeStatus.PARTIAL):
                    status = "success"
                elif ctx.status == EpisodeStatus.SKIPPED:
                    status = "skipped"
                else:
                    status = "failed"
                trash_path = (
                    ctx.trash_receipts[0].trash_path if ctx.trash_receipts else None
                )
                manifest_episodes.append(
                    EpisodeProcessed(
                        episode_path=str(ctx.scan_result.episode_path),
                        trash_receipt_path=str(trash_path) if trash_path else None,
                        show_name=ctx.scan_result.anime_title,
                        status=status,
                    )
                )
            manifest = RunManifest(
                run_id=undo_service.create_manifest_id(),
                timestamp=run_timestamp.isoformat(),
                library_path=str(pipeline_config.library_path),
                episodes_processed=tuple(manifest_episodes),
            )
            _raise_if_stopped(stop_event)
            await undo_service.save_manifest(manifest)
            _raise_if_stopped(stop_event)

        # Clear checkpoint on normal (not stopped) completion
        _raise_if_stopped(stop_event)
        if checkpoint_manager:
            await checkpoint_manager.clear()
            _raise_if_stopped(stop_event)

        _raise_if_stopped(stop_event)
        logger.info(
            "Pipeline completed successfully",
            stage="done",
            progress_current=len(scan_results),
            progress_total=len(scan_results),
        )
        return report

    async def _analyze_episode(
        self,
        scan: LibraryScanResult,
        anime_title: str,
        pipeline_config: PipelineConfig,
        run_timestamp: datetime,
        *,
        stop_event: asyncio.Event | None = None,
        font_resolver: FontResolver | None = None,
    ) -> EpisodeContext:
        """Run sequential timing repair, timing sync fallback, font extraction, font resolution, and mux planning for one episode."""
        _raise_if_stopped(stop_event)
        ctx = EpisodeContext(scan_result=scan, status=EpisodeStatus.FAILED)
        if scan.subtitle_path is None:
            return ctx.model_copy(
                update={
                    "status": EpisodeStatus.FAILED,
                    "errors": ["No subtitle path found for repair."],
                }
            )

        async with self._analysis_lock:
            _raise_if_stopped(stop_event)
            # 1. Timing check/repair
            try:
                _raise_if_stopped(stop_event)
                repaired_content = await asyncio.to_thread(
                    repair_ass, scan.subtitle_path
                )
                _raise_if_stopped(stop_event)
                ctx = ctx.model_copy(
                    update={
                        "repaired_content": repaired_content,
                        "status": EpisodeStatus.COMPLETE,  # temporarily COMPLETE until we check other things
                    }
                )
            except (PipelineStoppedError, asyncio.CancelledError):
                raise
            except Exception as e:
                logger.error(
                    "subtitle repair failed",
                    episode=scan.episode_path.name,
                    error=str(e),
                )
                return ctx.model_copy(
                    update={
                        "status": EpisodeStatus.FAILED,
                        "errors": [f"Subtitle repair failed: {e}"],
                    }
                )

            # Write repaired content to a temporary subtitle file
            temp_sub_path = scan.subtitle_path.with_name(
                f"{scan.subtitle_path.stem}.tmp.ass"
            )
            if not pipeline_config.dry_run:
                _raise_if_stopped(stop_event)
                await self.filesystem.write_file_atomic(temp_sub_path, repaired_content)
                _raise_if_stopped(stop_event)

            # 2. Timing Sync Fallback Chain
            if pipeline_config.sync_enabled:
                _raise_if_stopped(stop_event)
                sync_res = await self._sync_subtitle(
                    scan.episode_path,
                    temp_sub_path,
                    temp_sub_path,
                    stop_event=stop_event,
                )
                _raise_if_stopped(stop_event)
                ctx = ctx.model_copy(update={"sync_result": sync_res})
                if not sync_res.success:
                    # Sync failed, log error but do not halt, leave repaired subtitle intact
                    ctx = ctx.model_copy(
                        update={
                            "errors": ctx.errors
                            + [
                                "Subtitle sync failed. Using repaired unsynced subtitle."
                            ],
                            "status": EpisodeStatus.PARTIAL,
                        }
                    )
                else:
                    # Sync succeeded, read back the synced subtitle if not dry_run
                    if not pipeline_config.dry_run:

                        def _read_synced() -> str:
                            with open(temp_sub_path, "r", encoding="utf-8") as f:
                                return f.read()

                        try:
                            _raise_if_stopped(stop_event)
                            synced_content = await asyncio.to_thread(_read_synced)
                            _raise_if_stopped(stop_event)
                            ctx = ctx.model_copy(
                                update={"repaired_content": synced_content}
                            )
                        except (PipelineStoppedError, asyncio.CancelledError):
                            raise
                        except Exception as e:
                            logger.error(
                                "failed to read synced subtitle content", error=str(e)
                            )

            # 3. Font Extraction
            _raise_if_stopped(stop_event)
            font_queries = extract_fonts(
                ctx.repaired_content or "", scan.episode_path, anime_title
            )
            _raise_if_stopped(stop_event)
            ctx = ctx.model_copy(update={"font_queries": font_queries})

            # 4. Font Resolution (Sequential)
            resolved_fonts = []
            missing_fonts = []
            active_font_resolver = font_resolver or self.font_resolver
            for query in font_queries:
                _raise_if_stopped(stop_event)
                try:
                    asset = await active_font_resolver.resolve(query)
                    _raise_if_stopped(stop_event)
                    resolved_fonts.append(asset)
                except (PipelineStoppedError, asyncio.CancelledError):
                    raise
                except FontMatchError as e:
                    logger.warning(
                        "font resolution failed",
                        font=query.requested_name,
                        error=str(e),
                    )
                    missing_fonts.append(query.requested_name)
                    ctx = ctx.model_copy(update={"errors": ctx.errors + [str(e)]})
                except Exception as e:
                    logger.error(
                        "unexpected error during font resolution",
                        font=query.requested_name,
                        error=str(e),
                    )
                    missing_fonts.append(query.requested_name)
                    ctx = ctx.model_copy(
                        update={
                            "errors": ctx.errors
                            + [f"Resolution error for {query.requested_name}: {e}"]
                        }
                    )

            ctx = ctx.model_copy(
                update={
                    "resolved_fonts": resolved_fonts,
                    "missing_fonts": missing_fonts,
                }
            )

            # 5. Plan Mux
            _raise_if_stopped(stop_event)
            temp_mkv_path = scan.episode_path.with_name(
                f"{scan.episode_path.stem}.tmp.mkv"
            )
            job = plan_mux(ctx, temp_mkv_path, dry_run=pipeline_config.dry_run)
            _raise_if_stopped(stop_event)
            ctx = ctx.model_copy(update={"mux_job": job})

            return ctx

    async def _sync_subtitle(
        self,
        reference_mkv: Path,
        subtitle_ass: Path,
        output_ass: Path,
        *,
        stop_event: asyncio.Event | None = None,
    ) -> SyncResult:
        """Sync subtitle_ass to reference_mkv audio, falling back from alass to ffsubsync."""
        _raise_if_stopped(stop_event)
        duration_start = time.perf_counter()

        # Check if alass is available
        alass_available = (
            self.tool_registry.is_available("alass")
            or shutil.which("alass") is not None
        )

        if alass_available:
            from src.adapters.alass import AlassAdapter

            alass_adapter = AlassAdapter(self.subprocess_adapter)
            logger.info(
                "attempting subtitle sync via alass", subtitle=subtitle_ass.name
            )
            try:
                _raise_if_stopped(stop_event)
                res = await alass_adapter.sync(
                    reference_mkv,
                    subtitle_ass,
                    output_ass,
                    timeout=float(self.config.default_timeout_s),
                )
                _raise_if_stopped(stop_event)
                duration_ms = (time.perf_counter() - duration_start) * 1000.0
                if res.success:
                    offset = self._parse_offset(res.stdout or res.stderr)
                    return SyncResult(
                        success=True,
                        tool_used="alass",
                        tool_fallback_used=None,
                        offset_ms=offset,
                        duration_ms=duration_ms,
                    )
                else:
                    logger.warning(
                        "alass sync failed, falling back to ffsubsync", error=res.stderr
                    )
            except (PipelineStoppedError, asyncio.CancelledError):
                raise
            except Exception as e:
                logger.warning("alass execution encountered an exception", error=str(e))

        # Fallback to ffsubsync
        ffsubsync_available = (
            self.tool_registry.is_available("ffsubsync")
            or shutil.which("ffsubsync") is not None
        )
        if ffsubsync_available:
            _raise_if_stopped(stop_event)
            from src.adapters.ffsubsync import FfsubsyncAdapter

            ff_adapter = FfsubsyncAdapter(self.subprocess_adapter)
            logger.info(
                "attempting subtitle sync via ffsubsync", subtitle=subtitle_ass.name
            )
            try:
                _raise_if_stopped(stop_event)
                res = await ff_adapter.sync(
                    reference_mkv,
                    subtitle_ass,
                    output_ass,
                    timeout=float(self.config.default_timeout_s),
                )
                _raise_if_stopped(stop_event)
                duration_ms = (time.perf_counter() - duration_start) * 1000.0
                if res.success:
                    offset = self._parse_offset(res.stdout or res.stderr)
                    return SyncResult(
                        success=True,
                        tool_used="alass",
                        tool_fallback_used="ffsubsync",
                        offset_ms=offset,
                        duration_ms=duration_ms,
                    )
                else:
                    logger.error("ffsubsync sync failed as well", error=res.stderr)
            except (PipelineStoppedError, asyncio.CancelledError):
                raise
            except Exception as e:
                logger.error(
                    "ffsubsync execution encountered an exception", error=str(e)
                )

        _raise_if_stopped(stop_event)
        duration_ms = (time.perf_counter() - duration_start) * 1000.0
        # Both failed or both unavailable
        return SyncResult(
            success=False,
            tool_used="alass",
            tool_fallback_used="ffsubsync",
            offset_ms=0.0,
            duration_ms=duration_ms,
        )

    def _parse_offset(self, output: str) -> float:
        import re

        if not output:
            return 0.0
        match = re.search(
            r"(?:offset|shift|delay)\D*([-+]?\d*\.?\d+)", output, re.IGNORECASE
        )
        if match:
            try:
                val = float(match.group(1))
                if abs(val) < 20:
                    return val * 1000.0
                return val
            except ValueError:
                pass
        return 0.0
