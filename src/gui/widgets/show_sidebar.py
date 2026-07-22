from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFontMetrics,
    QIcon,
    QPainter,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.gui.signals import SignalBridge
from src.gui.theme import TOKENS, status_color, status_label
from src.models.pipeline import ShowStatus, ShowSummary


class ShowSidebarWidget(QWidget):
    """Show navigation with keyboard-accessible actions and bounded UI work."""

    show_selected = Signal(str, Path)  # (show_name, folder_path)
    add_folder_requested = Signal(object)  # Emits Path or None
    refresh_requested = Signal()  # Emits when explicit Refresh is requested

    def __init__(
        self, signal_bridge: SignalBridge, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._signal_bridge = signal_bridge
        self.setFixedWidth(TOKENS.sidebar_width)
        self.setAcceptDrops(True)
        self.setAccessibleName("Show library")
        self.setAccessibleDescription(
            "Navigate shows, add a library folder, or refresh the library index."
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            TOKENS.spacing_8,
            TOKENS.spacing_8,
            TOKENS.spacing_8,
            TOKENS.spacing_8,
        )
        layout.setSpacing(TOKENS.spacing_8)

        self._list_widget = QListWidget(self)
        self._list_widget.setAccessibleName("Shows")
        self._list_widget.setAccessibleDescription(
            "Shows in the active library. Use arrow keys and Enter to select a show."
        )
        self._list_widget.setToolTip("Select a show to view and run its episodes")
        self._list_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self._list_widget.itemActivated.connect(self._on_item_clicked)
        layout.addWidget(self._list_widget)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(TOKENS.spacing_8)

        self._add_btn = QPushButton("Add Folder", self)
        self._add_btn.setAccessibleName("Add library folder")
        self._add_btn.setAccessibleDescription(
            "Choose a folder to add to the Anime Studio library."
        )
        self._add_btn.setToolTip("Add a folder to the library")
        self._add_btn.clicked.connect(self._on_add_clicked)
        button_layout.addWidget(self._add_btn)

        self._refresh_btn = QPushButton("Refresh", self)
        self._refresh_btn.setAccessibleName("Refresh library index")
        self._refresh_btn.setAccessibleDescription(
            "Rescan the configured library and update the show list."
        )
        self._refresh_btn.setToolTip("Refresh library index (full rescan)")
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        button_layout.addWidget(self._refresh_btn)

        layout.addLayout(button_layout)
        QWidget.setTabOrder(self._list_widget, self._add_btn)
        QWidget.setTabOrder(self._add_btn, self._refresh_btn)

    def set_refresh_enabled(self, enabled: bool) -> None:
        """Enable or disable the refresh button."""
        self._refresh_btn.setEnabled(enabled)

    def set_navigation_enabled(self, enabled: bool) -> None:
        """Enable or disable controls that can change the active show."""
        self._list_widget.setEnabled(enabled)
        self._add_btn.setEnabled(enabled)
        self._refresh_btn.setEnabled(enabled)

    def is_refresh_enabled(self) -> bool:
        """Return whether the refresh button is enabled."""
        return self._refresh_btn.isEnabled()

    def populate(self, shows: list[ShowSummary]) -> None:
        """Populate the sidebar with the provided show summaries."""
        self._list_widget.clear()
        for show in shows:
            self.add_show(show)

    def add_show(self, show: ShowSummary) -> None:
        """Add a show to the sidebar or update its existing full-path entry."""
        for index in range(self._list_widget.count()):
            item = self._list_widget.item(index)
            item_show = cast(ShowSummary | None, item.data(Qt.ItemDataRole.UserRole))
            if item_show and item_show.path == show.path:
                self._set_item_presentation(item, show)
                return

        item = QListWidgetItem()
        self._set_item_presentation(item, show)
        self._list_widget.addItem(item)

    def update_show_status(self, path: Path, status: ShowStatus) -> None:
        """Update a show status by its full folder path."""
        for index in range(self._list_widget.count()):
            item = self._list_widget.item(index)
            show = cast(ShowSummary | None, item.data(Qt.ItemDataRole.UserRole))
            if show and show.path == path:
                self._set_item_presentation(
                    item,
                    ShowSummary(
                        name=show.name,
                        path=show.path,
                        status=status,
                        episode_count=show.episode_count,
                        processed_count=show.processed_count,
                        subtitle_text=show.subtitle_text,
                    ),
                )
                break

    def get_show_status(self, path: Path) -> ShowStatus | None:
        """Return the current sidebar status for a show path."""
        for index in range(self._list_widget.count()):
            show = cast(
                ShowSummary | None,
                self._list_widget.item(index).data(Qt.ItemDataRole.UserRole),
            )
            if show and show.path == path:
                return show.status
        return None

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-elide visible labels when the sidebar width changes."""
        super().resizeEvent(event)
        for index in range(self._list_widget.count()):
            item = self._list_widget.item(index)
            show = cast(ShowSummary | None, item.data(Qt.ItemDataRole.UserRole))
            if show:
                self._set_item_presentation(item, show)

    def _set_item_presentation(self, item: QListWidgetItem, show: ShowSummary) -> None:
        """Render a show row while retaining its full identity in item data."""
        viewport_width = max(
            self._list_widget.viewport().width(),
            TOKENS.sidebar_width - (TOKENS.spacing_8 * 2),
        )
        width = max(viewport_width - 44, 96)
        metrics = QFontMetrics(self._list_widget.font())
        title = metrics.elidedText(
            show.name.replace("\n", " "), Qt.TextElideMode.ElideRight, width
        )
        subtitle = metrics.elidedText(
            show.subtitle_text.replace("\n", " "),
            Qt.TextElideMode.ElideRight,
            width,
        )
        readable_status = status_label(show.status.value)
        item.setData(Qt.ItemDataRole.UserRole, show)
        item.setText(f"{title}\n{readable_status} · {subtitle}")
        item.setIcon(self._get_status_icon(show.status))
        item.setToolTip(
            f"{show.name}\n{show.path}\nStatus: {readable_status}\n{show.subtitle_text}"
        )
        item.setData(
            Qt.ItemDataRole.AccessibleTextRole,
            f"{show.name}, {readable_status}, {show.subtitle_text}",
        )
        item.setData(
            Qt.ItemDataRole.AccessibleDescriptionRole,
            f"Show folder: {show.path}",
        )

    def _on_current_item_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current:
            self._emit_selected(current)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Retain the explicit click hook for compatibility with existing callers."""
        self._emit_selected(item)

    def _emit_selected(self, item: QListWidgetItem) -> None:
        show = cast(ShowSummary | None, item.data(Qt.ItemDataRole.UserRole))
        if show:
            self.show_selected.emit(show.name, show.path)

    def _on_add_clicked(self) -> None:
        self.add_folder_requested.emit(None)

    def _on_refresh_clicked(self) -> None:
        self.refresh_requested.emit()

    def _get_status_icon(self, status: ShowStatus) -> QIcon:
        """Draw a semantic status dot; text labels preserve non-color meaning."""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(status_color(status.value)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()

        return QIcon(pixmap)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept local drops without performing filesystem work in the widget."""
        if any(
            url.isLocalFile() and url.toLocalFile() for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Delegate path validation and scanning to the application boundary."""
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if url.isLocalFile() and local_path:
                self.add_folder_requested.emit(Path(local_path))
                event.acceptProposedAction()
                return
        event.ignore()
