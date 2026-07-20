import pytest
from pathlib import Path
from src.models.pipeline import ShowSummary, ShowStatus
from src.core.show_index import ShowIndexManager


@pytest.mark.asyncio
async def test_show_index_load_missing(tmp_path: Path) -> None:
    """1. load() returns [] when file missing."""
    manager = ShowIndexManager(tmp_path)
    shows = await manager.load()
    assert shows == []


@pytest.mark.asyncio
async def test_show_index_round_trip(tmp_path: Path) -> None:
    """2. save() + load() round-trip preserves all ShowSummary fields."""
    manager = ShowIndexManager(tmp_path)
    original_shows = [
        ShowSummary(
            name="Wistoria Season 2",
            path=Path("D:/Anime/Wistoria Season 2"),
            status=ShowStatus.READY,
            episode_count=12,
            processed_count=2,
            subtitle_text="2 processed",
        ),
        ShowSummary(
            name="Hunter x Hunter",
            path=Path("D:/Anime/Hunter x Hunter"),
            status=ShowStatus.PENDING,
            episode_count=148,
            processed_count=0,
            subtitle_text="148 pending",
        ),
    ]

    await manager.save(original_shows)
    loaded_shows = await manager.load()

    assert len(loaded_shows) == 2
    assert loaded_shows[0].name == "Wistoria Season 2"
    assert loaded_shows[0].path == Path("D:/Anime/Wistoria Season 2")
    assert loaded_shows[0].status == ShowStatus.READY
    assert loaded_shows[0].episode_count == 12
    assert loaded_shows[0].processed_count == 2
    assert loaded_shows[0].subtitle_text == "2 processed"

    assert loaded_shows[1].name == "Hunter x Hunter"
    assert loaded_shows[1].status == ShowStatus.PENDING


@pytest.mark.asyncio
async def test_show_index_add_show(tmp_path: Path) -> None:
    """3. add_show() appends to existing list."""
    manager = ShowIndexManager(tmp_path)
    show1 = ShowSummary(
        name="Show 1",
        path=Path("D:/Anime/Show 1"),
        status=ShowStatus.PENDING,
        episode_count=10,
        processed_count=0,
        subtitle_text="10 episodes",
    )
    await manager.add_show(show1)

    shows = await manager.load()
    assert len(shows) == 1
    assert shows[0].name == "Show 1"

    show2 = ShowSummary(
        name="Show 2",
        path=Path("D:/Anime/Show 2"),
        status=ShowStatus.READY,
        episode_count=12,
        processed_count=0,
        subtitle_text="12 episodes",
    )
    await manager.add_show(show2)

    shows_after = await manager.load()
    assert len(shows_after) == 2
    assert shows_after[0].name == "Show 1"
    assert shows_after[1].name == "Show 2"


@pytest.mark.asyncio
async def test_show_index_update_status(tmp_path: Path) -> None:
    """4. update_status() changes status for correct path only."""
    manager = ShowIndexManager(tmp_path)
    path1 = Path("D:/Anime/Show 1")
    path2 = Path("D:/Anime/Show 2")
    shows = [
        ShowSummary(
            name="Show 1",
            path=path1,
            status=ShowStatus.PENDING,
            episode_count=10,
            processed_count=0,
            subtitle_text="10 episodes",
        ),
        ShowSummary(
            name="Show 2",
            path=path2,
            status=ShowStatus.PENDING,
            episode_count=12,
            processed_count=0,
            subtitle_text="12 episodes",
        ),
    ]
    await manager.save(shows)

    await manager.update_status(path1, ShowStatus.ALL_DONE)

    loaded = await manager.load()
    assert loaded[0].status == ShowStatus.ALL_DONE
    assert loaded[1].status == ShowStatus.PENDING  # Unchanged


@pytest.mark.asyncio
async def test_show_index_corrupt_toml(tmp_path: Path) -> None:
    """5. Corrupted TOML -> returns [] without exception."""
    manager = ShowIndexManager(tmp_path)
    # Write corrupted data to index path
    manager.index_path.parent.mkdir(parents=True, exist_ok=True)
    manager.index_path.write_text(
        "corrupted [ toml: = missing quotes", encoding="utf-8"
    )

    shows = await manager.load()
    assert shows == []
