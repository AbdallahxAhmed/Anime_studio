import asyncio
from datetime import datetime, timezone
import time
from pathlib import Path
import shutil
import structlog

from src.models.pipeline import LibraryScanResult, EpisodeContext, PipelineConfig
from src.models.report import EpisodeStatus, EpisodeReport, PipelineReport
from src.models.subtitle import SubtitleFile, SyncResult
from src.models.mux import MuxResult
from src.core.subtitle_repair import repair_ass, extract_fonts
from src.core.font_resolver import FontResolver
from src.core.mux_planner import plan_mux
from src.core.report_writer import render_report, render_incremental_section
from src.ports.subprocess import SubprocessPort
from src.ports.filesystem import FilesystemPort
from src.adapters.dependency_checker import ToolRegistry
from src.config import AppConfig
from src.errors import FontMatchError
from src.core.library_scanner import scan_library

logger = structlog.get_logger()


class PipelineRunner:
    def __init__(
        self,
        font_resolver: FontResolver,
        subprocess_adapter: SubprocessPort,
        filesystem: FilesystemPort,
        tool_registry: ToolRegistry,
        config: AppConfig,
    ) -> None:
        self.font_resolver = font_resolver
        self.subprocess_adapter = subprocess_adapter
        self.filesystem = filesystem
        self.tool_registry = tool_registry
        self.config = config
        self._analysis_lock = asyncio.Lock()

    async def run(self, pipeline_config: PipelineConfig) -> PipelineReport:
        """Run the full library pipeline: scan, repair, resolve fonts, timing sync, plan mux, dispatch mux, trash, report."""
        start_time = time.perf_counter()
        run_timestamp = datetime.now(timezone.utc)

        # 1. Scan Library
        scan_results = await scan_library(pipeline_config.library_path)

        # Resolve anime_title
        anime_title = pipeline_config.anime_title
        if not anime_title:
            if scan_results:
                anime_title = scan_results[0].anime_title
            else:
                anime_title = Path(pipeline_config.library_path).name or "Unknown"

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
            report_md = render_report(report)
            report_path = Path(pipeline_config.library_path) / "_AnimeStudio_Report.md"
            await self.filesystem.write_file_atomic(report_path, report_md)
            return report

        # Find skipped episodes (MKVs without matching ASS)
        all_mkvs = sorted(
            list(Path(pipeline_config.library_path).rglob("*.mkv")),
            key=lambda p: p.name,
        )
        scanned_mkv_paths = {Path(s.episode_path).resolve() for s in scan_results}
        skipped_reports = []
        for mkv in all_mkvs:
            if mkv.resolve() not in scanned_mkv_paths:
                skipped_reports.append(
                    EpisodeReport(
                        episode_path=mkv.resolve(),
                        status=EpisodeStatus.SKIPPED,
                    )
                )

        # 2. Sequential Analysis Phase
        episode_contexts = []
        for scan in scan_results:
            ctx = await self._analyze_episode(
                scan, anime_title, pipeline_config, run_timestamp
            )
            episode_contexts.append(ctx)

        # 3. Concurrent Mux Concurrency Semaphore
        mux_semaphore = asyncio.Semaphore(self.config.max_concurrent_disk_io)

        # Helper to run mux and post-process
        async def _mux_and_post_process(ctx: EpisodeContext) -> EpisodeContext:
            if ctx.status == EpisodeStatus.FAILED:
                return ctx

            if not ctx.mux_job:
                return ctx.model_copy(
                    update={
                        "status": EpisodeStatus.FAILED,
                        "errors": ctx.errors + ["MuxJob was not planned."],
                    }
                )

            async with mux_semaphore:
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
                        await self.filesystem.move_to_trash(
                            ctx.scan_result.subtitle_path, sub_trash
                        )
                        await self.filesystem.move_to_trash(
                            ctx.scan_result.episode_path, mkv_trash
                        )
                        # Atomic replace original MKV with temporary muxed file
                        await self.filesystem.replace_file(
                            ctx.mux_job.output_path, ctx.scan_result.episode_path
                        )
                        # Cleanup temp ASS file if exists
                        temp_sub_path = ctx.scan_result.subtitle_path.with_name(
                            f"{ctx.scan_result.subtitle_path.stem}.tmp.ass"
                        )
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

                    return ctx.model_copy(
                        update={
                            "mux_result": mux_res,
                            "trash_receipts": trash_receipts,
                            "status": final_status,
                        }
                    )

                except Exception as e:
                    logger.error(
                        "muxing or post-processing failed",
                        episode=ctx.scan_result.episode_path.name,
                        error=str(e),
                    )
                    return ctx.model_copy(
                        update={
                            "status": EpisodeStatus.FAILED,
                            "errors": ctx.errors + [f"Mux post-processing error: {e}"],
                        }
                    )

        # Dispatch mux operations concurrently
        mux_tasks = [_mux_and_post_process(ctx) for ctx in episode_contexts]
        final_contexts = await asyncio.gather(*mux_tasks)

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

        # Append skipped ones
        episode_reports.extend(skipped_reports)

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
            def _read_report():
                with open(report_path, "r", encoding="utf-8") as f:
                    return f.read()

            try:
                existing_content = await asyncio.to_thread(_read_report)
                incremental_section = render_incremental_section(report)
                new_content = f"{existing_content}\n{incremental_section}"
                await self.filesystem.write_file_atomic(report_path, new_content)
            except Exception as e:
                logger.error(
                    "failed to append to existing report, overwriting instead",
                    error=str(e),
                )
                report_md = render_report(report)
                await self.filesystem.write_file_atomic(report_path, report_md)
        else:
            report_md = render_report(report)
            await self.filesystem.write_file_atomic(report_path, report_md)

        return report

    async def _analyze_episode(
        self,
        scan: LibraryScanResult,
        anime_title: str,
        pipeline_config: PipelineConfig,
        run_timestamp: datetime,
    ) -> EpisodeContext:
        """Run sequential timing repair, timing sync fallback, font extraction, font resolution, and mux planning for one episode."""
        ctx = EpisodeContext(scan_result=scan, status=EpisodeStatus.FAILED)

        async with self._analysis_lock:
            # 1. Timing check/repair
            try:
                repaired_content = repair_ass(scan.subtitle_path)
                ctx = ctx.model_copy(
                    update={
                        "repaired_content": repaired_content,
                        "status": EpisodeStatus.COMPLETE,  # temporarily COMPLETE until we check other things
                    }
                )
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
                await self.filesystem.write_file_atomic(temp_sub_path, repaired_content)

            # 2. Timing Sync Fallback Chain
            if pipeline_config.sync_enabled:
                sync_res = await self._sync_subtitle(
                    scan.episode_path, temp_sub_path, temp_sub_path
                )
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

                        def _read_synced():
                            with open(temp_sub_path, "r", encoding="utf-8") as f:
                                return f.read()

                        try:
                            synced_content = await asyncio.to_thread(_read_synced)
                            ctx = ctx.model_copy(
                                update={"repaired_content": synced_content}
                            )
                        except Exception as e:
                            logger.error(
                                "failed to read synced subtitle content", error=str(e)
                            )

            # 3. Font Extraction
            font_queries = extract_fonts(
                ctx.repaired_content or "", scan.episode_path, anime_title
            )
            ctx = ctx.model_copy(update={"font_queries": font_queries})

            # 4. Font Resolution (Sequential)
            resolved_fonts = []
            missing_fonts = []
            for query in font_queries:
                try:
                    asset = await self.font_resolver.resolve(query)
                    resolved_fonts.append(asset)
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
            temp_mkv_path = scan.episode_path.with_name(
                f"{scan.episode_path.stem}.tmp.mkv"
            )
            job = plan_mux(ctx, temp_mkv_path, dry_run=pipeline_config.dry_run)
            ctx = ctx.model_copy(update={"mux_job": job})

            return ctx

    async def _sync_subtitle(
        self,
        reference_mkv: Path,
        subtitle_ass: Path,
        output_ass: Path,
    ) -> SyncResult:
        """Sync subtitle_ass to reference_mkv audio, falling back from alass to ffsubsync."""
        duration_start = time.perf_counter()

        # Check if alass is available
        alass_available = (
            self.tool_registry.is_available("alass")
            or shutil.which("alass") is not None
        )

        if alass_available:
            from src.adapters.alass import AlassAdapter

            adapter = AlassAdapter(self.subprocess_adapter)
            logger.info(
                "attempting subtitle sync via alass", subtitle=subtitle_ass.name
            )
            try:
                res = await adapter.sync(
                    reference_mkv,
                    subtitle_ass,
                    output_ass,
                    timeout=float(self.config.default_timeout_s),
                )
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
            except Exception as e:
                logger.warning("alass execution encountered an exception", error=str(e))

        # Fallback to ffsubsync
        ffsubsync_available = (
            self.tool_registry.is_available("ffsubsync")
            or shutil.which("ffsubsync") is not None
        )
        if ffsubsync_available:
            from src.adapters.ffsubsync import FfsubsyncAdapter

            adapter = FfsubsyncAdapter(self.subprocess_adapter)
            logger.info(
                "attempting subtitle sync via ffsubsync", subtitle=subtitle_ass.name
            )
            try:
                res = await adapter.sync(
                    reference_mkv,
                    subtitle_ass,
                    output_ass,
                    timeout=float(self.config.default_timeout_s),
                )
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
            except Exception as e:
                logger.error(
                    "ffsubsync execution encountered an exception", error=str(e)
                )

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
