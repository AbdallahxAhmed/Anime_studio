import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from src.models.pipeline import ShowSummary, ShowStatus
from src.gui.signals import SignalBridge
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
    assert "Wistoria Season 2" in item1.text()
    assert "2 processed" in item1.text()

    item2 = sidebar._list_widget.item(1)
    assert "Hunter x Hunter" in item2.text()


def test_sidebar_show_selected_signal(mocker) -> None:
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

    mock_slot = mocker.Mock()
    sidebar.show_selected.connect(mock_slot)

    item = sidebar._list_widget.item(0)
    sidebar._on_item_clicked(item)

    mock_slot.assert_called_once_with(
        "Wistoria Season 2", Path("D:/Entertainment/Anime/Wistoria Season 2")
    )


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
    """5. ALL_DONE shows green icon (QPainter color check)."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)

    icon = sidebar._get_status_icon(ShowStatus.ALL_DONE)
    pixmap = icon.pixmap(16, 16)
    image = pixmap.toImage()
    # Check the color at center (8, 8)
    color = image.pixelColor(8, 8)
    assert color.name() == "#7ed321"

    icon_warning = sidebar._get_status_icon(ShowStatus.WARNING)
    pixmap_warning = icon_warning.pixmap(16, 16)
    image_warning = pixmap_warning.toImage()
    color_warning = image_warning.pixelColor(8, 8)
    assert color_warning.name() == "#e8572a"


def test_sidebar_empty_populate() -> None:
    """6. Empty populate([]) shows empty state without crash."""
    bridge = SignalBridge()
    sidebar = ShowSidebarWidget(signal_bridge=bridge)
    sidebar.populate([])
    assert sidebar._list_widget.count() == 0
