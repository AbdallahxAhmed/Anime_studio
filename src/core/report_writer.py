import structlog
from src.models.report import PipelineReport, EpisodeStatus

logger = structlog.get_logger()


def render_report(report: PipelineReport) -> str:
    """Render PipelineReport to markdown string."""
    logger.info("rendering pipeline report", anime_title=report.anime_title)

    lines = []
    lines.append(f"# Anime Studio Pipeline Report: {report.anime_title}")
    lines.append("")
    lines.append(
        f"- **Run Timestamp**: {report.run_timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    lines.append(f"- **Total Duration**: {report.duration_ms / 1000:.2f}s")
    lines.append(f"- **Total Fonts Found**: {report.total_fonts_found}")
    lines.append("")

    # Emojis for status
    status_map = {
        EpisodeStatus.COMPLETE: "✓ COMPLETE",
        EpisodeStatus.PARTIAL: "⚠ PARTIAL",
        EpisodeStatus.FAILED: "✗ FAILED",
        EpisodeStatus.SKIPPED: "➖ SKIPPED",
    }

    lines.append("## Episode Summary")
    lines.append("")
    lines.append(
        "| Episode | Status | Subtitle Sync | Mux Duration | Fonts Attached | Missing Fonts |"
    )
    lines.append(
        "|---------|--------|---------------|--------------|----------------|---------------|"
    )

    for ep in report.episodes:
        ep_name = ep.episode_path.name

        status_str = status_map.get(ep.status, str(ep.status).upper())

        sync_str = "N/A"
        if ep.subtitle_result:
            s_res = ep.subtitle_result
            sync_str = "✓ Synced" if s_res.success else "✗ Failed"
            sync_str += f" ({s_res.tool_used}"
            if s_res.tool_fallback_used:
                sync_str += f" -> {s_res.tool_fallback_used}"
            sync_str += f", {s_res.offset_ms:.1f}ms)"

        mux_str = "N/A"
        fonts_attached = 0
        if ep.mux_result:
            m_res = ep.mux_result
            mux_str = "✓ Success" if m_res.success else "✗ Failed"
            mux_str += f" ({m_res.duration_ms / 1000:.2f}s)"
            fonts_attached = m_res.fonts_attached

        missing_fonts_str = ", ".join(ep.missing_fonts) if ep.missing_fonts else "None"

        lines.append(
            f"| {ep_name} | {status_str} | {sync_str} | {mux_str} | {fonts_attached} | {missing_fonts_str} |"
        )

    lines.append("")

    # Applied Rules Section
    lines.append("## Applied Rules")
    lines.append("")
    has_rules = False
    for ep in report.episodes:
        if ep.applied_rules:
            has_rules = True
            lines.append(f"### {ep.episode_path.name}")
            for rule in ep.applied_rules:
                lines.append(f"- {rule}")
    if not has_rules:
        lines.append("No automated rules applied during this run.")
    lines.append("")

    # Genuine Misses Section
    lines.append("## Genuine Misses")
    lines.append("")
    if report.genuine_misses:
        for miss in report.genuine_misses:
            lines.append(f"- {miss}")
    else:
        lines.append("Zero genuine misses. All fonts resolved successfully.")
    lines.append("")

    return "\n".join(lines)


def render_incremental_section(report: PipelineReport) -> str:
    """Render a delimited section for appending to an existing report."""
    logger.info(
        "rendering incremental pipeline section", anime_title=report.anime_title
    )
    timestamp_str = report.run_timestamp.strftime("%Y-%m-%d %H:%M:%S")

    report_content = render_report(report)

    lines = []
    lines.append("---")
    lines.append(f"## Incremental Run: {timestamp_str}")
    lines.append("")
    lines.append(report_content)

    return "\n".join(lines)
