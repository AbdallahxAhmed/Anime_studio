import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtGui import QColor
from src.models.pipeline import LibraryScanResult
from src.gui.widgets.episode_table import EpisodeTableWidget, StatusBadgeDelegate


@pytest.fixture(scope="session", autouse=True)
def q_app() -> QApplication:
    """Ensure a QApplication instance exists for GUI unit testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_table_instantiation() -> None:
    """1. Widget instantiates without error."""
    table = EpisodeTableWidget()
    assert table is not None
    assert table._model.rowCount() == 0


def test_table_populate() -> None:
    """2. populate() shows correct row count."""
    table = EpisodeTableWidget()
    episodes = [
        LibraryScanResult(
            episode_path=Path("D:/Anime/show/ep1.mkv"),
            subtitle_path=Path("D:/Anime/show/ep1.ass"),
            anime_title="Show",
        ),
        LibraryScanResult(
            episode_path=Path("D:/Anime/show/ep2.mkv"),
            subtitle_path=None,
            anime_title="Show",
        ),
    ]
    table.populate(episodes)
    assert table._model.rowCount() == 2

    # Check status
    assert table._model.data(table._model.index(0, 3)) == "pending"
    assert table._model.data(table._model.index(1, 3)) == "skipped"


def test_table_get_selected_paths_empty() -> None:
    """3. get_selected_paths() returns empty when nothing checked."""
    table = EpisodeTableWidget()
    episodes = [
        LibraryScanResult(episode_path=Path("ep1.mkv"), anime_title="Show"),
    ]
    table.populate(episodes)
    table.set_all_checked(False)
    assert table.get_selected_paths() == []


def test_table_set_all_checked() -> None:
    """4. set_all_checked(True) selects all rows."""
    table = EpisodeTableWidget()
    episodes = [
        LibraryScanResult(episode_path=Path("ep1.mkv"), anime_title="Show"),
        LibraryScanResult(episode_path=Path("ep2.mkv"), anime_title="Show"),
    ]
    table.populate(episodes)
    table.set_all_checked(False)
    assert len(table.get_selected_paths()) == 0
    table.set_all_checked(True)
    assert len(table.get_selected_paths()) == 2


def test_table_selection_changed_signal(mocker) -> None:
    """5. selection_changed signal emits when checkbox toggled."""
    table = EpisodeTableWidget()
    episodes = [
        LibraryScanResult(episode_path=Path("ep1.mkv"), anime_title="Show"),
    ]
    table.populate(episodes)

    mock_slot = mocker.Mock()
    table.selection_changed.connect(mock_slot)

    # Toggle checkbox on first row
    table._model.setData(
        table._model.index(0, 0),
        Qt.CheckState.Unchecked,
        Qt.ItemDataRole.CheckStateRole,
    )

    mock_slot.assert_called_with([])


def test_table_badge_pending_color(mocker) -> None:
    """6. Status 'pending' row shows amber in delegate (mock QPainter)."""
    delegate = StatusBadgeDelegate()

    # Mock model index returning "pending"
    mock_index = mocker.MagicMock(spec=QModelIndex)
    mock_index.column.return_value = 3
    mock_index.data.return_value = "pending"

    mock_painter = mocker.MagicMock()
    mock_font = mocker.MagicMock()
    mock_painter.font.return_value = mock_font

    option = QStyleOptionViewItem()
    option.rect = QStyleOptionViewItem().rect

    delegate.paint(mock_painter, option, mock_index)

    # Verify setBrush was called with the color #f5a623 (case-insensitive check)
    mock_painter.setBrush.assert_called_once()
    called_color = mock_painter.setBrush.call_args[0][0]
    assert called_color == QColor("#F5A623")


def test_table_badge_skipped_color(mocker) -> None:
    """7. Status 'skipped' row shows gray."""
    delegate = StatusBadgeDelegate()

    # Mock model index returning "skipped"
    mock_index = mocker.MagicMock(spec=QModelIndex)
    mock_index.column.return_value = 3
    mock_index.data.return_value = "skipped"

    mock_painter = mocker.MagicMock()
    mock_font = mocker.MagicMock()
    mock_painter.font.return_value = mock_font

    option = QStyleOptionViewItem()
    option.rect = QStyleOptionViewItem().rect

    delegate.paint(mock_painter, option, mock_index)

    mock_painter.setBrush.assert_called_once()
    called_color = mock_painter.setBrush.call_args[0][0]
    assert called_color == QColor("#888888")


def test_table_update_episode_status(tmp_path: Path) -> None:
    """8. update_episode_status() changes status for correct full path using tmp_path."""
    table = EpisodeTableWidget()
    path1 = tmp_path / "show" / "ep1.mkv"
    path2 = tmp_path / "show" / "ep2.mkv"
    episodes = [
        LibraryScanResult(episode_path=path1, anime_title="Show"),
        LibraryScanResult(episode_path=path2, anime_title="Show"),
    ]
    table.populate(episodes)

    table.update_episode_status(path1, "muxed")
    assert table._model.data(table._model.index(0, 3)) == "muxed"
    assert table._model.data(table._model.index(1, 3)) == "skipped"  # Unchanged


def test_table_update_status_same_filename_different_directories(
    tmp_path: Path,
) -> None:
    """Regression test: duplicate filenames in different directories do not collide."""
    table = EpisodeTableWidget()
    path_s1 = tmp_path / "Season 1" / "episode01.mkv"
    path_s2 = tmp_path / "Season 2" / "episode01.mkv"

    episodes = [
        LibraryScanResult(
            episode_path=path_s1,
            subtitle_path=tmp_path / "Season 1" / "episode01.ass",
            anime_title="Show S1",
        ),
        LibraryScanResult(
            episode_path=path_s2,
            subtitle_path=tmp_path / "Season 2" / "episode01.ass",
            anime_title="Show S2",
        ),
    ]
    table.populate(episodes)

    # Update Season 2 episode01.mkv only
    table.update_episode_status(path_s2, "complete")

    # Season 1 episode01.mkv must remain pending, Season 2 episode01.mkv updated
    assert table._model.data(table._model.index(0, 3)) == "pending"
    assert table._model.data(table._model.index(1, 3)) == "complete"


def test_table_populate_zero_episodes_selection_state(mocker) -> None:
    """Task 1: Population with zero episodes produces zero selected paths."""
    table = EpisodeTableWidget()
    mock_slot = mocker.Mock()
    table.selection_changed.connect(mock_slot)
    table.populate([])
    assert table.get_selected_paths() == []
    mock_slot.assert_called_once_with([])


def test_table_populate_n_episodes_selection_state_synchronized(mocker) -> None:
    """Task 1: Population with N episodes synchronizes checkboxes, selected paths, and emitted count."""
    table = EpisodeTableWidget()
    mock_slot = mocker.Mock()
    table.selection_changed.connect(mock_slot)

    episodes = [
        LibraryScanResult(episode_path=Path("ep1.mkv"), anime_title="Show"),
        LibraryScanResult(episode_path=Path("ep2.mkv"), anime_title="Show"),
        LibraryScanResult(episode_path=Path("ep3.mkv"), anime_title="Show"),
    ]
    table.populate(episodes)

    # All N episodes checked by default in model
    selected = table.get_selected_paths()
    assert len(selected) == 3
    assert selected == [Path("ep1.mkv"), Path("ep2.mkv"), Path("ep3.mkv")]

    # Check emission during populate
    mock_slot.assert_called_with(selected)


def test_table_select_single_and_multiple_rows(mocker) -> None:
    """Task 1: Selecting 1 row or multiple rows emits exact count."""
    table = EpisodeTableWidget()
    episodes = [
        LibraryScanResult(episode_path=Path("ep1.mkv"), anime_title="Show"),
        LibraryScanResult(episode_path=Path("ep2.mkv"), anime_title="Show"),
    ]
    table.populate(episodes)

    mock_slot = mocker.Mock()
    table.selection_changed.connect(mock_slot)

    # Uncheck all, then check row 0
    table.set_all_checked(False)
    assert table.get_selected_paths() == []

    table._model.setData(
        table._model.index(0, 0),
        Qt.CheckState.Checked,
        Qt.ItemDataRole.CheckStateRole,
    )
    assert table.get_selected_paths() == [Path("ep1.mkv")]
    mock_slot.assert_called_with([Path("ep1.mkv")])

    table._model.setData(
        table._model.index(1, 0),
        Qt.CheckState.Checked,
        Qt.ItemDataRole.CheckStateRole,
    )
    assert table.get_selected_paths() == [Path("ep1.mkv"), Path("ep2.mkv")]
    mock_slot.assert_called_with([Path("ep1.mkv"), Path("ep2.mkv")])


def test_table_repopulate_resets_selection_count(mocker) -> None:
    """Task 1: Re-populating table with another show resets selection count correctly."""
    table = EpisodeTableWidget()
    table.populate(
        [
            LibraryScanResult(episode_path=Path("showA_ep1.mkv"), anime_title="Show A"),
            LibraryScanResult(episode_path=Path("showA_ep2.mkv"), anime_title="Show A"),
        ]
    )
    assert len(table.get_selected_paths()) == 2

    # Re-populate with Show B (1 episode)
    table.populate(
        [
            LibraryScanResult(episode_path=Path("showB_ep1.mkv"), anime_title="Show B"),
        ]
    )
    assert len(table.get_selected_paths()) == 1
    assert table.get_selected_paths() == [Path("showB_ep1.mkv")]
