from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from src.gui.theme import TOKENS, canonical_status, status_color, status_label
from src.models.pipeline import LibraryScanResult


class EpisodeTableModel(QAbstractTableModel):
    """Model for episode selection and processing status."""

    COLUMNS = ["Select", "Episode", "Subtitle", "Status"]

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
        self._statuses = [
            "pending" if episode.subtitle_path else "skipped" for episode in episodes
        ]
        self.endResetModel()

    def get_selected_paths(self) -> list[Path]:
        """Return the paths of all selected episodes."""
        return [
            self._episodes[index].episode_path
            for index, selected in enumerate(self._selected)
            if selected
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
        return len(self.COLUMNS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._episodes)):
            return None

        row = index.row()
        column = index.column()
        episode = self._episodes[row]
        episode_path = str(episode.episode_path)

        if column == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return (
                    Qt.CheckState.Checked
                    if self._selected[row]
                    else Qt.CheckState.Unchecked
                )
            if role == Qt.ItemDataRole.ToolTipRole:
                return f"Select episode: {episode_path}"
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return f"Select {episode.episode_path.name}"
            if role == Qt.ItemDataRole.AccessibleDescriptionRole:
                return episode_path
            return None

        if column == 1:
            if role == Qt.ItemDataRole.DisplayRole:
                return episode.episode_path.name
            if role in {
                Qt.ItemDataRole.ToolTipRole,
                Qt.ItemDataRole.AccessibleDescriptionRole,
            }:
                return episode_path
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return f"Episode {episode.episode_path.name}"
            return None

        if column == 2:
            subtitle_text = self._subtitle_text(episode)
            if role == Qt.ItemDataRole.DisplayRole:
                return subtitle_text
            if role == Qt.ItemDataRole.ToolTipRole:
                return (
                    str(episode.subtitle_path)
                    if episode.subtitle_path
                    else subtitle_text
                )
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return f"Subtitle: {subtitle_text}"
            if role == Qt.ItemDataRole.AccessibleDescriptionRole:
                return (
                    str(episode.subtitle_path)
                    if episode.subtitle_path
                    else subtitle_text
                )
            return None

        if column == 3:
            readable_status = status_label(self._statuses[row])
            if role == Qt.ItemDataRole.DisplayRole:
                return readable_status
            if role in {
                Qt.ItemDataRole.ToolTipRole,
                Qt.ItemDataRole.AccessibleTextRole,
                Qt.ItemDataRole.AccessibleDescriptionRole,
            }:
                return f"Episode status: {readable_status}"
            return None

        return None

    @staticmethod
    def _subtitle_text(episode: LibraryScanResult) -> str:
        if episode.subtitle_path:
            return episode.subtitle_path.name
        if episode.embedded_sub_info and episode.embedded_sub_info.tracks:
            languages = episode.embedded_sub_info.languages
            language_suffix = f" ({', '.join(languages)})" if languages else ""
            return f"Embedded{language_suffix}"
        return "None"

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
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        if section == 0 and role == Qt.ItemDataRole.ToolTipRole:
            return "Select or deselect all episodes"
        if section == 0 and role == Qt.ItemDataRole.AccessibleTextRole:
            return "Select all episodes"
        return None

    def update_status(self, path: Path, status: str) -> None:
        """Update status for a specific full episode path."""
        for index, episode in enumerate(self._episodes):
            if episode.episode_path == path:
                self._statuses[index] = canonical_status(status)
                model_index = self.index(index, 3)
                self.dataChanged.emit(
                    model_index,
                    model_index,
                    [
                        Qt.ItemDataRole.DisplayRole,
                        Qt.ItemDataRole.ToolTipRole,
                        Qt.ItemDataRole.AccessibleTextRole,
                    ],
                )
                break


class StatusBadgeDelegate(QStyledItemDelegate):
    """Custom delegate for semantic, textual status badges."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        if index.column() != 3:
            super().paint(painter, option, index)
            return

        status = canonical_status(str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
        background_color = QColor(status_color(status))
        label = status_label(status)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if option.state & QStyle.StateFlag.State_Selected:  # type: ignore[attr-defined]  # PySide6 QStyleOptionViewItem inherits state from QStyleOption
            painter.fillRect(option.rect, option.palette.highlight())  # type: ignore[attr-defined]  # PySide6 QStyleOptionViewItem inherits rect/palette from QStyleOption

        badge_rect = option.rect.adjusted(  # type: ignore[attr-defined]  # PySide6 QStyleOptionViewItem inherits rect from QStyleOption
            TOKENS.spacing_4,
            TOKENS.spacing_4,
            -TOKENS.spacing_4,
            -TOKENS.spacing_4,
        )
        painter.setBrush(background_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, TOKENS.radius_small, TOKENS.radius_small)

        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(TOKENS.text_on_accent))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        return QSize(TOKENS.status_column_width, TOKENS.table_row_height)


class EpisodeTableWidget(QWidget):
    """Episode selection table with keyboard controls and textual status badges."""

    selection_changed = Signal(list)  # list[Path]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Episode selection")
        self.setAccessibleDescription(
            "Select the episodes to run, review subtitle availability, and track status."
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableView(self)
        self._table.setAccessibleName("Episodes")
        self._table.setAccessibleDescription(
            "Episode rows. Use Space to select a row and Control+A to select all."
        )
        self._table.setToolTip("Select episodes to include in the next run")
        self._table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._model = EpisodeTableModel(self)
        self._table.setModel(self._model)

        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setDefaultSectionSize(TOKENS.table_row_height)

        self._table.setItemDelegateForColumn(3, StatusBadgeDelegate(self))

        header = self._table.horizontalHeader()
        header.setAccessibleName("Episode columns")
        header.setAccessibleDescription(
            "Select all episodes from the Select column header."
        )
        header.setToolTip("Click Select to select or deselect all episodes")
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        self._table.setColumnWidth(0, TOKENS.select_column_width)
        self._table.setColumnWidth(2, 180)
        self._table.setColumnWidth(3, TOKENS.status_column_width)

        layout.addWidget(self._table)

        self._model.dataChanged.connect(self._on_selection_updated)
        header.sectionClicked.connect(self._on_header_clicked)
        self._table.installEventFilter(self)
        self._all_selected = True

    def populate(self, episodes: list[LibraryScanResult]) -> None:
        """Populate the table with episodes."""
        self._model.populate(episodes)
        self._all_selected = bool(episodes)
        self._on_selection_updated()

    def get_selected_paths(self) -> list[Path]:
        """Return paths of checked episodes."""
        return self._model.get_selected_paths()

    def update_episode_status(self, path: Path, status: str) -> None:
        """Update dynamic status of an episode by its full path."""
        self._model.update_status(path, status)

    def set_all_checked(self, checked: bool) -> None:
        """Select or deselect all episodes."""
        self._model.set_all_checked(checked)
        self._all_selected = checked

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Make Control+A select episode checkboxes rather than only table cells."""
        if (
            watched is self._table
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.matches(QKeySequence.StandardKey.SelectAll)
        ):
            self.set_all_checked(True)
            return True
        return super().eventFilter(watched, event)

    def _on_header_checkbox_clicked(self, checked: bool) -> None:
        self.set_all_checked(checked)

    def _on_header_clicked(self, logical_index: int) -> None:
        if logical_index == 0:
            self._on_header_checkbox_clicked(not self._all_selected)

    def _on_selection_updated(self, *_args: object) -> None:
        selected_paths = self.get_selected_paths()
        self._all_selected = bool(selected_paths) and (
            len(selected_paths) == self._model.rowCount()
        )
        self.selection_changed.emit(selected_paths)
