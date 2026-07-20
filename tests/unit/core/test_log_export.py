import pytest
from src.core.log_export import format_log_entry, export_log_to_file


def test_format_log_entry_full():
    entry = {
        "timestamp": "2026-06-06T15:30:45.123456Z",
        "level": "info",
        "event": "Finished processing episode",
        "episode": "ep01.mkv",
        "duration_ms": 1500.5,
    }
    expected = "[15:30:45] [INFO] Finished processing episode | duration_ms=1500.5 | episode=ep01.mkv"
    assert format_log_entry(entry) == expected


def test_format_log_entry_missing_fields():
    # Test missing timestamp
    entry_no_ts = {
        "level": "error",
        "event": "Database connection failed",
        "retry_count": 3,
    }
    assert "??:??:??" in format_log_entry(entry_no_ts)
    assert "[ERROR]" in format_log_entry(entry_no_ts)
    assert "Database connection failed" in format_log_entry(entry_no_ts)

    # Test completely empty dict
    assert "??:??:??" in format_log_entry({})
    assert "[INFO]" in format_log_entry({})


@pytest.mark.anyio
async def test_export_log_to_file_writes_content(tmp_path):
    entries = [
        {
            "timestamp": "2026-06-06T12:00:00Z",
            "level": "info",
            "event": "Start session",
        },
        {
            "timestamp": "2026-06-06T12:05:00Z",
            "level": "warning",
            "event": "Low disk space",
            "free_gb": 5,
        },
    ]
    dest = tmp_path / "test_export.txt"
    await export_log_to_file(entries, dest)

    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert len(lines) == 2
    assert lines[0] == "[12:00:00] [INFO] Start session"
    assert lines[1] == "[12:05:00] [WARNING] Low disk space | free_gb=5"
