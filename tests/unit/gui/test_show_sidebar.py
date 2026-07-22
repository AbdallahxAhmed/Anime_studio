import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from src.models.pipeline import ShowSummary, ShowStatus
from src.gui.signals import SignalBridge
from src.gui.theme import TOKENS
from src.gui.widgets.show_sidebar import ShowSidebarWidget


@pytest.fixture(scope="session", autouse=True)
def q_app() -> QApplication:
    """Ensure a QApplication instance exists for GUI unit testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_sidebar_instantiation() -> None:
    """1. Widget instantiates without error."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)
    assert sidebar.width() == 220
    assert sidebar.acceptDrops() is True


def test_sidebar_populate_shows() -> None:
    """2. populate() fills list with correct show count."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)
    shows = [
        ShowSummary(
            name="Wistoria Season 2",
            path=Path("D:/Entertainment/Anime/Wistoria Season 2"),
            status=ShowStatus.READY,
            episode_count=12,
            processed_count=2,
            subtitle_text="2 processed / 10 pending",
        ),
        ShowSummary(
            name="Hunter x Hunter",
            path=Path("D:/Entertainment/Anime/Hunter x Hunter"),
            status=ShowStatus.PENDING,
            episode_count=148,
            processed_count=0,
            subtitle_text="148 pending",
        ),
    ]
    sidebar.populate(shows)
    assert sidebar._list_widget.count() == 2

    item1 = sidebar._list_widget.item(0)
    assert "Ready" in item1.text()
    assert "2 processed" in item1.text()
    assert "Wistoria Season 2" in item1.toolTip()

    item2 = sidebar._list_widget.item(1)
    assert "Pending" in item2.text()
    assert "Hunter x Hunter" in item2.toolTip()


def test_sidebar_show_selected_signal() -> None:
    """3. Clicking a show emits show_selected with correct (name, path)."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)
    show = ShowSummary(
        name="Wistoria Season 2",
        path=Path("D:/Entertainment/Anime/Wistoria Season 2"),
        status=ShowStatus.READY,
        episode_count=12,
        processed_count=2,
        subtitle_text="2 processed",
    )
    sidebar.add_show(show)

    emissions: list[tuple[str, Path]] = []
    sidebar.show_selected.connect(lambda name, path: emissions.append((name, path)))

    item = sidebar._list_widget.item(0)
    sidebar._on_item_clicked(item)

    assert emissions == [
        ("Wistoria Season 2", Path("D:/Entertainment/Anime/Wistoria Season 2"))
    ]


def test_sidebar_update_show_status() -> None:
    """4. update_show_status() changes icon for correct show."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)
    path = Path("D:/Entertainment/Anime/Wistoria Season 2")
    show = ShowSummary(
        name="Wistoria Season 2",
        path=path,
        status=ShowStatus.PENDING,
        episode_count=12,
        processed_count=2,
        subtitle_text="2 processed",
    )
    sidebar.add_show(show)

    item = sidebar._list_widget.item(0)
    # Update status to processing
    sidebar.update_show_status(path, ShowStatus.PROCESSING)

    updated_show = item.data(Qt.ItemDataRole.UserRole)
    assert updated_show.status == ShowStatus.PROCESSING


def test_sidebar_status_icon_color_check() -> None:
    """5. Status dots use the centralized semantic token colors."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)

    icon = sidebar._get_status_icon(ShowStatus.ALL_DONE)
    pixmap = icon.pixmap(16, 16)
    image = pixmap.toImage()
    # Check the color at center (8, 8)
    color = image.pixelColor(8, 8)
    assert color.name() == TOKENS.success.casefold()

    icon_warning = sidebar._get_status_icon(ShowStatus.WARNING)
    pixmap_warning = icon_warning.pixmap(16, 16)
    image_warning = pixmap_warning.toImage()
    color_warning = image_warning.pixelColor(8, 8)
    assert color_warning.name() == TOKENS.warning.casefold()


def test_sidebar_empty_populate() -> None:
    """6. Empty populate([]) shows empty state without crash."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)
    sidebar.populate([])
    assert sidebar._list_widget.count() == 0


def test_sidebar_refresh_button_discoverability() -> None:
    """Task 3: Refresh button has visible text 'Refresh', tooltip, and emits refresh_requested."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)

    assert sidebar._refresh_btn.text() == "Refresh"
    assert sidebar._refresh_btn.toolTip() == "Refresh library index (full rescan)"
    assert sidebar._refresh_btn.accessibleName() == "Refresh library index"

    refresh_count = 0

    def record_refresh() -> None:
        nonlocal refresh_count
        refresh_count += 1

    sidebar.refresh_requested.connect(record_refresh)

    sidebar._refresh_btn.click()
    assert refresh_count == 1
    sidebar.set_refresh_enabled(False)
    sidebar._refresh_btn.click()
    assert refresh_count == 1


def test_sidebar_accessibility_and_keyboard_navigation(qtbot) -> None:
    """The sidebar has discoverable actions and keyboard selection."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)
    qtbot.addWidget(sidebar)
    sidebar.populate(
        [
            ShowSummary(
                name="Show A",
                path=Path("C:/library/Show A"),
                status=ShowStatus.READY,
                episode_count=1,
                processed_count=0,
                subtitle_text="1 pending",
            ),
            ShowSummary(
                name="Show B",
                path=Path("C:/library/Show B"),
                status=ShowStatus.PENDING,
                episode_count=1,
                processed_count=0,
                subtitle_text="1 pending",
            ),
        ]
    )

    assert sidebar.accessibleName() == "Show library"
    assert sidebar._list_widget.accessibleName() == "Shows"
    assert sidebar._add_btn.toolTip() == "Add a folder to the library"

    with qtbot.waitSignal(sidebar.show_selected) as signal:
        sidebar._list_widget.setCurrentRow(1)
    assert signal.args == ["Show B", Path("C:/library/Show B")]

    sidebar.show()
    sidebar._list_widget.setFocus()
    with qtbot.waitSignal(sidebar.show_selected) as activated:
        qtbot.keyClick(sidebar._list_widget, Qt.Key.Key_Return)
    assert activated.args == ["Show B", Path("C:/library/Show B")]

    with qtbot.waitSignal(sidebar.add_folder_requested) as add_requested:
        sidebar._add_btn.setFocus()
        qtbot.keyClick(sidebar._add_btn, Qt.Key.Key_Space)
    assert add_requested.args == [None]


def test_sidebar_long_identity_is_elided_but_full_path_is_available() -> None:
    """Long show strings retain their full identity in tooltip and accessibility data."""
    sidebar = ShowSidebarWidget(signal_bridge=SignalBridge())
    long_name = "Very long English العربية 日本語 show title " * 4
    path = Path("C:/library") / long_name
    sidebar.add_show(
        ShowSummary(
            name=long_name,
            path=path,
            status=ShowStatus.READY,
            episode_count=1,
            processed_count=0,
            subtitle_text="Long subtitle " * 8,
        )
    )

    item = sidebar._list_widget.item(0)
    assert str(path) in item.toolTip()
    assert long_name in item.data(Qt.ItemDataRole.AccessibleTextRole)
    assert not hasattr(sidebar, "_has_mkv_files")
