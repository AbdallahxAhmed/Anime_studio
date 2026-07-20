from pathlib import Path
from typing import Any
from PySide6.QtCore import (
    Qt,
    Signal,
    QModelIndex,
    QPersistentModelIndex,
    QAbstractTableModel,
    QSize,
)
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableView,
    QHeaderView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
)
from src.models.pipeline import LibraryScanResult


class EpisodeTableModel(QAbstractTableModel):
    """Model for episode selection and processing status."""

    COLUMNS = ["", "Episode", "Subtitle", "Status"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._episodes: list[LibraryScanResult] = []
        self._selected: list[bool] = []
        self._statuses: list[str] = []

    def populate(self, episodes: list[LibraryScanResult]) -> None:
        """Populate the model with episodes and set initial status/selection."""
        self.beginResetModel()
        self._episodes = episodes
        self._selected = [True] * len(episodes)
        self._statuses = []
        for ep in episodes:
            if ep.subtitle_path:
                self._statuses.append("pending")
            else:
                self._statuses.append("skipped")
        self.endResetModel()

    def get_selected_paths(self) -> list[Path]:
        """Return the paths of all selected episodes."""
        return [
            self._episodes[i].episode_path
            for i, sel in enumerate(self._selected)
            if sel
        ]

    def set_all_checked(self, checked: bool) -> None:
        """Select or deselect all episodes."""
        if not self._episodes:
            return
        self._selected = [checked] * len(self._episodes)
        self.dataChanged.emit(
            self.index(0, 0),
            self.index(len(self._episodes) - 1, 0),
            [Qt.ItemDataRole.CheckStateRole],
        )

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return len(self._episodes)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return 4

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._episodes)):
            return None

        row = index.row()
        col = index.column()
        ep = self._episodes[row]

        if col == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return (
                    Qt.CheckState.Checked
                    if self._selected[row]
                    else Qt.CheckState.Unchecked
                )
            return None

        elif col == 1:
            if role == Qt.ItemDataRole.DisplayRole:
                return ep.episode_path.name
            return None

        elif col == 2:
            if role == Qt.ItemDataRole.DisplayRole:
                if ep.subtitle_path:
                    return ep.subtitle_path.name
                elif ep.embedded_sub_info and ep.embedded_sub_info.tracks:
                    langs = ep.embedded_sub_info.languages
                    lang_str = f" ({', '.join(langs)})" if langs else ""
                    return f"Embedded{lang_str}"
                return "None"
            return None

        elif col == 3:
            if role == Qt.ItemDataRole.DisplayRole:
                return self._statuses[row]
            return None

        return None

    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if (
            not index.isValid()
            or index.column() != 0
            or not (0 <= index.row() < len(self._episodes))
        ):
            return False

        if role == Qt.ItemDataRole.CheckStateRole:
            self._selected[index.row()] = (
                value == Qt.CheckState.Checked.value or value == Qt.CheckState.Checked
            )
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base_flags: Qt.ItemFlag = (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        if index.column() == 0:
            return base_flags | Qt.ItemFlag.ItemIsUserCheckable
        return base_flags

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return self.COLUMNS[section]
        return None

    def update_status(self, path: Path, status: str) -> None:
        """Update status for a specific episode path."""
        for i, ep in enumerate(self._episodes):
            if ep.episode_path == path:
                self._statuses[i] = status
                idx = self.index(i, 3)
                self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole])
                break


class StatusBadgeDelegate(QStyledItemDelegate):
    """Custom delegate for status badge styling."""

    COLORS = {
        "muxed": QColor("#7ED321"),
        "pending": QColor("#F5A623"),
        "skipped": QColor("#888888"),
        "error": QColor("#E8572A"),
    }

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        if index.column() != 3:
            super().paint(painter, option, index)
            return

        status = str(index.data(Qt.ItemDataRole.DisplayRole) or "").lower()
        bg_color = self.COLORS.get(status, QColor("#888888"))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw default background (selection highlight)
        if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]  # PySide6 QStyleOptionViewItem inherits state from QStyleOption
            painter.fillRect(option.rect, option.palette.highlight())  # type: ignore[attr-defined]  # PySide6 QStyleOptionViewItem inherits rect/palette from QStyleOption

        rect = option.rect.adjusted(6, 6, -6, -6)  # type: ignore[attr-defined]  # PySide6 QStyleOptionViewItem inherits rect from QStyleOption
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 4, 4)

        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, status.capitalize())

        painter.restore()

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        return QSize(100, 36)


class EpisodeTableWidget(QWidget):
    """Widget wrapper around QTableView containing EpisodeTableModel."""

    selection_changed = Signal(list)  # list[Path]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableView(self)
        self._model = EpisodeTableModel(self)
        self._table.setModel(self._model)

        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)

        # Badge delegate
        self._table.setItemDelegateForColumn(3, StatusBadgeDelegate(self))

        # Horizontal header setup
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        self._table.setColumnWidth(0, 30)
        self._table.setColumnWidth(2, 180)
        self._table.setColumnWidth(3, 100)

        layout.addWidget(self._table)

        # Wire data changes to selection emission
        self._model.dataChanged.connect(self._on_selection_updated)
        header.sectionClicked.connect(self._on_header_clicked)
        self._all_selected = True

    def populate(self, episodes: list[LibraryScanResult]) -> None:
        """Populate the table with episodes."""
        self._model.populate(episodes)
        self._all_selected = True
        self._on_selection_updated()

    def get_selected_paths(self) -> list[Path]:
        """Return paths of checked episodes."""
        return self._model.get_selected_paths()

    def update_episode_status(self, path: Path, status: str) -> None:
        """Update dynamic status of an episode by its path."""
        self._model.update_status(path, status)

    def set_all_checked(self, checked: bool) -> None:
        """Select or deselect all episodes."""
        self._model.set_all_checked(checked)
        self._all_selected = checked

    def _on_header_checkbox_clicked(self, checked: bool) -> None:
        self.set_all_checked(checked)

    def _on_header_clicked(self, logicalIndex: int) -> None:
        if logicalIndex == 0:
            self._on_header_checkbox_clicked(not self._all_selected)

    def _on_selection_updated(self, *args: Any) -> None:
        self.selection_changed.emit(self.get_selected_paths())
