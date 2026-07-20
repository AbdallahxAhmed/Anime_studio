from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QIcon,
    QPixmap,
    QPainter,
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
)
from src.models.pipeline import ShowSummary, ShowStatus
from src.gui.signals import SignalBridge


class ShowSidebarWidget(QWidget):
    """Sidebar widget displaying shows and status icons with drag-and-drop capability."""

    show_selected = Signal(str, Path)  # (show_name, folder_path)
    add_folder_requested = Signal(object)  # Emits Path or None
    refresh_requested = Signal()  # Emits when explicit Refresh is requested

    def __init__(
        self, signal_bridge: SignalBridge, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._signal_bridge = signal_bridge
        self.setFixedWidth(220)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self._list_widget = QListWidget(self)
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list_widget)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(5)

        self._add_btn = QPushButton("Add folder", self)
        self._add_btn.clicked.connect(self._on_add_clicked)
        btn_layout.addWidget(self._add_btn)

        self._refresh_btn = QPushButton("↻", self)
        self._refresh_btn.setToolTip("Refresh Library Index (Full Rescan)")
        self._refresh_btn.setFixedWidth(32)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        btn_layout.addWidget(self._refresh_btn)

        layout.addLayout(btn_layout)

    def set_refresh_enabled(self, enabled: bool) -> None:
        """Enable or disable the refresh button."""
        self._refresh_btn.setEnabled(enabled)

    def is_refresh_enabled(self) -> bool:
        """Return whether the refresh button is enabled."""
        return self._refresh_btn.isEnabled()

    def populate(self, shows: list[ShowSummary]) -> None:
        """Populate the sidebar with list of shows."""
        self._list_widget.clear()
        for show in shows:
            self.add_show(show)

    def add_show(self, show: ShowSummary) -> None:
        """Add a show to the sidebar or update if already present."""
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            item_show = item.data(Qt.ItemDataRole.UserRole)
            if item_show and item_show.path == show.path:
                item.setData(Qt.ItemDataRole.UserRole, show)
                item.setText(f"{show.name}\n{show.subtitle_text}")
                item.setIcon(self._get_status_icon(show.status))
                return

        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, show)
        item.setText(f"{show.name}\n{show.subtitle_text}")
        item.setIcon(self._get_status_icon(show.status))
        self._list_widget.addItem(item)

    def update_show_status(self, path: Path, status: ShowStatus) -> None:
        """Update status icon for a show by its folder path."""
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            show = item.data(Qt.ItemDataRole.UserRole)
            if show and show.path == path:
                updated = ShowSummary(
                    name=show.name,
                    path=show.path,
                    status=status,
                    episode_count=show.episode_count,
                    processed_count=show.processed_count,
                    subtitle_text=show.subtitle_text,
                )
                item.setData(Qt.ItemDataRole.UserRole, updated)
                item.setIcon(self._get_status_icon(status))
                break

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        show = item.data(Qt.ItemDataRole.UserRole)
        if show:
            self.show_selected.emit(show.name, show.path)

    def _on_add_clicked(self) -> None:
        self.add_folder_requested.emit(None)

    def _on_refresh_clicked(self) -> None:
        self.refresh_requested.emit()

    def _get_status_icon(self, status: ShowStatus) -> QIcon:
        """Draw a status icon circle using QPainter."""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color_map = {
            ShowStatus.PENDING: QColor("#888888"),
            ShowStatus.PROCESSING: QColor("#4A90D9"),
            ShowStatus.READY: QColor("#F5A623"),
            ShowStatus.ALL_DONE: QColor("#7ED321"),
            ShowStatus.NO_SUBTITLE: QColor("#BBBBBB"),
            ShowStatus.WARNING: QColor("#E8572A"),
        }
        color = color_map.get(status, QColor("#888888"))

        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()

        return QIcon(pixmap)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.is_dir():
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.is_dir():
                    if self._has_mkv_files(p):
                        self.add_folder_requested.emit(p)
                        event.acceptProposedAction()
                        return
        event.ignore()

    def _has_mkv_files(self, path: Path) -> bool:
        try:
            for child in path.iterdir():
                if child.is_file() and child.suffix.lower() == ".mkv":
                    return True
        except Exception:
            pass
        return False
