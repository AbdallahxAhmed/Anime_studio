import pytest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from src.gui.widgets.selection_tree import SelectionTreeWidget
from src.models.pipeline import (
    ShowNode,
    SubFolderNode,
    EpisodeContext,
    LibraryScanResult,
)
from src.models.report import EpisodeStatus


@pytest.fixture(scope="session", autouse=True)
def q_app() -> QApplication:
    """Ensure a QApplication instance exists for GUI unit testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_mock_show_tree() -> tuple[ShowNode, ...]:
    # Set up some mock ShowNode and SubFolderNode tree for testing populate
    scan1 = LibraryScanResult(
        episode_path=Path("/anime/Show A/episode_01.mkv"),
        subtitle_path=Path("/anime/Show A/episode_01.ass"),
        anime_title="Show A",
    )
    ctx1 = EpisodeContext(scan_result=scan1, status=EpisodeStatus.FAILED)

    scan2 = LibraryScanResult(
        episode_path=Path("/anime/Show A/Season 1/episode_02.mkv"),
        subtitle_path=Path("/anime/Show A/Season 1/episode_02.ass"),
        anime_title="Show A",
    )
    ctx2 = EpisodeContext(scan_result=scan2, status=EpisodeStatus.FAILED)

    sf1 = SubFolderNode(
        name="Season 1",
        path=Path("/anime/Show A/Season 1"),
        episodes=(ctx2,),
    )

    show_a = ShowNode(
        name="Show A",
        path=Path("/anime/Show A"),
        sub_folders=(sf1,),
        episodes=(ctx1,),
    )

    scan3 = LibraryScanResult(
        episode_path=Path("/anime/Show B/episode_03.mkv"),
        subtitle_path=Path("/anime/Show B/episode_03.ass"),
        anime_title="Show B",
    )
    ctx3 = EpisodeContext(scan_result=scan3, status=EpisodeStatus.FAILED)

    show_b = ShowNode(
        name="Show B",
        path=Path("/anime/Show B"),
        sub_folders=(),
        episodes=(ctx3,),
    )

    return (show_a, show_b)


def test_populate_creates_nodes() -> None:
    widget = SelectionTreeWidget()
    tree = _make_mock_show_tree()
    widget.populate(tree)

    # 2 top level shows
    root = widget._tree.invisibleRootItem()
    assert root.childCount() == 2

    # Check Show A
    item_a = root.child(0)
    assert "Show A" in item_a.text(0)
    assert item_a.childCount() == 1
    assert item_a.checkState(0) == Qt.CheckState.Checked

    # Check Season 1 child
    item_sf = item_a.child(0)
    assert "Season 1" in item_sf.text(0)
    assert item_sf.checkState(0) == Qt.CheckState.Checked

    # Check Show B
    item_b = root.child(1)
    assert "Show B" in item_b.text(0)
    assert item_b.childCount() == 0
    assert item_b.checkState(0) == Qt.CheckState.Checked


def test_get_selected_paths_all_checked() -> None:
    widget = SelectionTreeWidget()
    tree = _make_mock_show_tree()
    widget.populate(tree)

    selected = widget.get_selected_paths()
    expected = frozenset(
        {
            Path("/anime/Show A/Season 1"),
            Path("/anime/Show B"),
        }
    )
    # Wait, get_selected_paths only returns LEAF paths!
    # For Show A, it has subfolders, so Season 1 is the leaf.
    # For Show B, it has no subfolders, so Show B is the leaf.
    assert selected == expected


def test_get_selected_paths_partial() -> None:
    widget = SelectionTreeWidget()
    tree = _make_mock_show_tree()
    widget.populate(tree)

    # Uncheck Season 1
    root = widget._tree.invisibleRootItem()
    item_a = root.child(0)
    item_sf = item_a.child(0)
    item_sf.setCheckState(0, Qt.CheckState.Unchecked)

    selected = widget.get_selected_paths()
    # Season 1 unchecked -> only Show B selected (Show A's only subfolder is unchecked)
    assert Path("/anime/Show A/Season 1") not in selected
    assert Path("/anime/Show B") in selected


def test_select_all_deselect_all_buttons() -> None:
    widget = SelectionTreeWidget()
    tree = _make_mock_show_tree()
    widget.populate(tree)

    widget._deselect_all_btn.click()
    assert len(widget.get_selected_paths()) == 0

    widget._select_all_btn.click()
    assert len(widget.get_selected_paths()) == 2


def test_populate_empty_shows_placeholder() -> None:
    widget = SelectionTreeWidget()
    widget.populate(())
    root = widget._tree.invisibleRootItem()
    assert root.childCount() == 1
    assert root.child(0).text(0) == "No shows found"
    assert root.child(0).checkState(0) == Qt.CheckState.Unchecked
