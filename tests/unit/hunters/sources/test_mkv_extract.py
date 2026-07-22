import asyncio
import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock

from src.errors import PipelineStoppedError
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


def _query(episode_path: Path) -> FontQuery:
    return FontQuery(
        requested_name="TestTTF Regular",
        anime_title="Scoped Show",
        episode_path=episode_path,
    )


def _identify_result(attachments: list[dict[str, object]]) -> ToolResult:
    return ToolResult(
        tool_name="mkvmerge",
        success=True,
        exit_code=0,
        stdout=json.dumps({"attachments": attachments}),
        stderr="",
        duration_ms=1.0,
    )


@pytest.mark.anyio
async def test_mkv_extract_hunter_for_run_enumerates_only_selected_show(
    tmp_path: Path,
) -> None:
    library_root = tmp_path / "Library"
    show_a = library_root / "Show A"
    show_b = library_root / "Show B"
    show_a.mkdir(parents=True)
    show_b.mkdir()
    episode_a = show_a / "episode_01.mkv"
    episode_b = show_b / "episode_01.mkv"
    episode_a.touch()
    episode_b.touch()

    identified_paths: list[Path] = []

    async def execute(args: list[str], timeout: float | None = None) -> ToolResult:
        del timeout
        assert args[0] == "mkvmerge"
        identified_paths.append(Path(args[-1]))
        return _identify_result([])

    subprocess_port = AsyncMock()
    subprocess_port.execute.side_effect = execute
    base_hunter = MkvExtractHunter(subprocess_port)
    show_a_hunter = base_hunter.for_run(show_a)

    assert await show_a_hunter.search(_query(episode_a)) == []
    assert identified_paths == [episode_a]
    assert show_a_hunter.scope.discovery_root == show_a.resolve()
    assert base_hunter.scope.discovery_root is None


@pytest.mark.anyio
async def test_mkv_extract_hunter_legacy_library_path_searches_full_root(
    tmp_path: Path,
) -> None:
    library_root = tmp_path / "Library"
    show_a = library_root / "Show A"
    show_b = library_root / "Show B"
    show_a.mkdir(parents=True)
    show_b.mkdir()
    episode_a = show_a / "episode_01.mkv"
    episode_b = show_b / "episode_01.mkv"
    episode_a.touch()
    episode_b.touch()

    identified_paths: list[Path] = []

    async def execute(args: list[str], timeout: float | None = None) -> ToolResult:
        del timeout
        identified_paths.append(Path(args[-1]))
        return _identify_result([])

    subprocess_port = AsyncMock()
    subprocess_port.execute.side_effect = execute
    hunter = MkvExtractHunter(subprocess_port, library_root)

    assert await hunter.search(_query(episode_a)) == []
    assert identified_paths == [episode_a, episode_b]


@pytest.mark.anyio
async def test_mkv_extract_hunter_scope_isolates_negative_and_positive_caches(
    tmp_path: Path,
) -> None:
    library_root = tmp_path / "Library"
    show_a = library_root / "Show A"
    show_b = library_root / "Show B"
    show_a.mkdir(parents=True)
    show_b.mkdir()
    episode_a = show_a / "episode_01.mkv"
    episode_b = show_b / "episode_01.mkv"
    episode_a.touch()
    episode_b.touch()
    fixture_font = Path("tests/fixtures/fonts/valid.ttf").read_bytes()
    execute_calls: list[tuple[str, Path]] = []

    async def execute(args: list[str], timeout: float | None = None) -> ToolResult:
        del timeout
        if args[0] == "mkvmerge":
            mkv_path = Path(args[-1])
            execute_calls.append(("mkvmerge", mkv_path))
            if mkv_path == episode_a:
                return _identify_result([])
            return _identify_result(
                [
                    {
                        "content_type": "application/x-truetype-font",
                        "file_name": "valid.ttf",
                        "id": 7,
                    }
                ]
            )
        assert args[0] == "mkvextract"
        execute_calls.append(("mkvextract", Path(args[-2])))
        temp_file_path = Path(args[-1].split(":", 1)[1])
        temp_file_path.write_bytes(fixture_font)
        return ToolResult(
            tool_name="mkvextract",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
        )

    subprocess_port = AsyncMock()
    subprocess_port.execute.side_effect = execute
    base_hunter = MkvExtractHunter(subprocess_port)
    show_a_hunter = base_hunter.for_run(show_a)
    show_b_hunter = base_hunter.for_run(show_b)

    assert await show_a_hunter.search(_query(episode_a)) == []
    assert await show_a_hunter.search(_query(episode_a)) == []
    show_a_identifies = [
        path
        for command, path in execute_calls
        if command == "mkvmerge" and path == episode_a
    ]
    assert show_a_identifies == [episode_a]

    show_b_results = await show_b_hunter.search(_query(episode_b))
    assert len(show_b_results) == 1
    assert show_b_results[0].font_asset is not None
    assert show_b_results[0].font_asset.file_path == episode_b
    assert ("mkvmerge", episode_b) in execute_calls
    show_b_payload = await show_b_hunter.download(show_b_results[0])
    assert show_b_payload.metadata["discovery_root"] == str(show_b.resolve())
    assert show_b_payload.metadata["scope_identity"] == show_b_hunter.scope.identity

    call_count = len(execute_calls)
    cached_results = await show_b_hunter.search(_query(episode_b))
    assert len(cached_results) == 1
    assert cached_results[0].query.episode_path == episode_b
    assert len(execute_calls) == call_count


@pytest.mark.anyio
async def test_mkv_extract_hunter_concurrent_scopes_do_not_share_discovery_state(
    tmp_path: Path,
) -> None:
    library_root = tmp_path / "Library"
    show_a = library_root / "Show A"
    show_b = library_root / "Show B"
    show_a.mkdir(parents=True)
    show_b.mkdir()
    episode_a = show_a / "episode_01.mkv"
    episode_b = show_b / "episode_01.mkv"
    episode_a.touch()
    episode_b.touch()

    identifies_started = asyncio.Event()
    release_identifies = asyncio.Event()
    identified_paths: list[Path] = []

    async def execute(args: list[str], timeout: float | None = None) -> ToolResult:
        del timeout
        identified_paths.append(Path(args[-1]))
        if len(identified_paths) == 2:
            identifies_started.set()
        await release_identifies.wait()
        return _identify_result([])

    subprocess_port = AsyncMock()
    subprocess_port.execute.side_effect = execute
    base_hunter = MkvExtractHunter(subprocess_port)
    show_a_hunter = base_hunter.for_run(show_a)
    show_b_hunter = base_hunter.for_run(show_b)

    task_a = asyncio.create_task(show_a_hunter.search(_query(episode_a)))
    task_b = asyncio.create_task(show_b_hunter.search(_query(episode_b)))
    await identifies_started.wait()
    release_identifies.set()

    assert await task_a == []
    assert await task_b == []
    assert set(identified_paths) == {episode_a, episode_b}
    assert show_a_hunter.scope.identity != show_b_hunter.scope.identity
    assert show_a_hunter._attachments == []
    assert show_b_hunter._attachments == []


@pytest.mark.anyio
async def test_mkv_extract_hunter_stop_during_directory_enumeration_is_neutral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    show = tmp_path / "Show"
    show.mkdir()
    episode = show / "episode_01.mkv"
    episode.touch()
    stop_event = asyncio.Event()

    from src.hunters.sources import mkv_extract

    original_to_thread = mkv_extract.asyncio.to_thread

    async def stop_after_listing(
        function: object, *args: object, **kwargs: object
    ) -> object:
        result = await original_to_thread(function, *args, **kwargs)
        stop_event.set()
        return result

    monkeypatch.setattr(mkv_extract.asyncio, "to_thread", stop_after_listing)
    subprocess_port = AsyncMock()
    hunter = MkvExtractHunter(subprocess_port).for_run(show, stop_event)

    with pytest.raises(PipelineStoppedError):
        await hunter.search(_query(episode))

    subprocess_port.execute.assert_not_called()
    assert hunter._scanned is False
    assert hunter._attachments == []


@pytest.mark.anyio
async def test_mkv_extract_hunter_native_cancellation_clears_partial_scan_state(
    tmp_path: Path,
) -> None:
    show = tmp_path / "Show"
    show.mkdir()
    episode = show / "episode_01.mkv"
    episode.touch()
    identify_started = asyncio.Event()
    finish_identify = asyncio.Event()

    async def execute(args: list[str], timeout: float | None = None) -> ToolResult:
        del args, timeout
        identify_started.set()
        await finish_identify.wait()
        return _identify_result([])

    subprocess_port = AsyncMock()
    subprocess_port.execute.side_effect = execute
    hunter = MkvExtractHunter(subprocess_port, show)
    search_task = asyncio.create_task(hunter.search(_query(episode)))
    await identify_started.wait()
    search_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await search_task

    assert hunter._scanned is False
    assert hunter._attachments == []
