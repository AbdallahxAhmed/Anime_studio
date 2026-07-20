import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock

from src.hunters.sources.mkv_extract import MkvExtractHunter
from src.models.font import FontQuery
from src.models.tool_result import ToolResult


def test_mkv_extract_hunter_supports() -> None:
    subprocess_port = AsyncMock()
    hunter = MkvExtractHunter(subprocess_port)
    query = FontQuery(
        requested_name="TestTTF",
        anime_title="Test",
        episode_path=Path("ep1.mkv"),
    )
    assert hunter.supports(query) is True


@pytest.mark.anyio
async def test_mkv_extract_hunter_search_and_download(tmp_path: Path) -> None:
    library_path = tmp_path / "library"
    library_path.mkdir()
    mkv_path = library_path / "episode1.mkv"
    mkv_path.touch()

    mkvmerge_json = {
        "attachments": [
            {
                "content_type": "application/x-truetype-font",
                "file_name": "valid.ttf",
                "id": 1,
            },
            {"content_type": "text/plain", "file_name": "notes.txt", "id": 2},
        ]
    }

    mkvmerge_result = ToolResult(
        tool_name="mkvmerge",
        success=True,
        exit_code=0,
        stdout=json.dumps(mkvmerge_json),
        stderr="",
        duration_ms=5.0,
    )

    async def mock_execute(args: list[str], timeout: float | None = None) -> ToolResult:
        if "mkvmerge" in args[0]:
            return mkvmerge_result
        elif "mkvextract" in args[0]:
            extract_arg = args[-1]
            temp_file_path = Path(extract_arg.split(":", 1)[1])
            with open("tests/fixtures/fonts/valid.ttf", "rb") as f:
                temp_file_path.write_bytes(f.read())
            return ToolResult(
                tool_name="mkvextract",
                success=True,
                exit_code=0,
                stdout="extracted",
                stderr="",
                duration_ms=10.0,
            )
        return ToolResult(
            tool_name="",
            success=False,
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=0.0,
        )

    subprocess_port = AsyncMock()
    subprocess_port.execute.side_effect = mock_execute

    hunter = MkvExtractHunter(subprocess_port, library_path)

    # Search for correct internal name
    query = FontQuery(
        requested_name="TestTTF Regular",
        anime_title="Test",
        episode_path=mkv_path,
    )

    results = await hunter.search(query)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].font_asset is not None
    assert results[0].font_asset.name == "TestTTF Regular"
    assert results[0].font_asset.file_path == mkv_path

    # Second search should use cache
    subprocess_port.execute.reset_mock()
    subprocess_port.execute.side_effect = mock_execute
    results2 = await hunter.search(query)
    assert len(results2) == 1
    subprocess_port.execute.assert_not_called()

    payload = await hunter.download(results[0])
    assert payload.font_name == "TestTTF Regular"
    assert len(payload.font_data) > 0
    assert payload.file_extension == ".ttf"
    assert payload.metadata["mkv_path"] == str(mkv_path)
    assert payload.metadata["attachment_id"] == "1"


@pytest.mark.anyio
async def test_mkv_extract_hunter_no_attachments(tmp_path: Path) -> None:
    library_path = tmp_path / "library"
    library_path.mkdir()
    mkv_path = library_path / "episode1.mkv"
    mkv_path.touch()

    mkvmerge_result = ToolResult(
        tool_name="mkvmerge",
        success=True,
        exit_code=0,
        stdout='{"attachments": []}',
        stderr="",
        duration_ms=5.0,
    )
    subprocess_port = AsyncMock()
    subprocess_port.execute.return_value = mkvmerge_result

    hunter = MkvExtractHunter(subprocess_port, library_path)
    query = FontQuery(
        requested_name="TestTTF Regular",
        anime_title="Test",
        episode_path=mkv_path,
    )
    results = await hunter.search(query)
    assert len(results) == 0


@pytest.mark.anyio
async def test_mkv_extract_hunter_subprocess_failure(tmp_path: Path) -> None:
    library_path = tmp_path / "library"
    library_path.mkdir()
    mkv_path = library_path / "episode1.mkv"
    mkv_path.touch()

    mkvmerge_result = ToolResult(
        tool_name="mkvmerge",
        success=False,
        exit_code=1,
        stdout="",
        stderr="error",
        duration_ms=5.0,
    )
    subprocess_port = AsyncMock()
    subprocess_port.execute.return_value = mkvmerge_result

    hunter = MkvExtractHunter(subprocess_port, library_path)
    query = FontQuery(
        requested_name="TestTTF Regular",
        anime_title="Test",
        episode_path=mkv_path,
    )
    results = await hunter.search(query)
    assert len(results) == 0
