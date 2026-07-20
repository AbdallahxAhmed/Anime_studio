from typing import Any
import asyncio
from datetime import datetime
from pathlib import Path


def format_log_entry(entry: dict[str, Any]) -> str:
    ts = entry.get("timestamp", "")
    # Parse ISO timestamp → HH:MM:SS
    try:
        # ISO timestamp can end with Z or include timezone info, fromisoformat handles it in Python 3.11+
        # If there's a Z, replace it or let fromisoformat parse it if it supports it (Python 3.11 does)
        if isinstance(ts, str) and ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        time_str = dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        time_str = "??:??:??"

    level = str(entry.get("level", "info")).upper()
    event = entry.get("event", "")

    # Exclude internal structlog keys
    skip_keys = {"timestamp", "level", "event", "logger", "_record", "_logger"}
    extras = {k: v for k, v in entry.items() if k not in skip_keys}
    # Sort extras alphabetically to ensure deterministic output
    extras_str = " | ".join(f"{k}={v}" for k, v in sorted(extras.items()))

    line = f"[{time_str}] [{level}] {event}"
    if extras_str:
        line += f" | {extras_str}"
    return line


async def export_log_to_file(
    entries: list[dict[str, Any]],
    dest_path: Path,
) -> None:
    lines = [format_log_entry(e) for e in entries]
    content = "\n".join(lines)
    await asyncio.to_thread(_write_text, dest_path, content)


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
