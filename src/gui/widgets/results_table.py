import logging
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from src.gui.messages import EpisodeResult, EpisodeStatus, PipelineRunResult
from src.gui.theme import TOKENS, status_color

logger = logging.getLogger("anime_studio.gui.widgets.results_table")


class ResultsTableModel(QAbstractTableModel):
    """Virtual model for pipeline outcomes with readable status semantics."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[EpisodeResult] = []
        self.headers = ["Episode", "Status", "Fonts Found", "Fonts Missing", "Details"]

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return len(self.results)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return len(self.headers)

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
            return self.headers[section]
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self.results)):
            return None

        result = self.results[index.row()]
        column = index.column()
        status_text = self._status_text(result.status)
        full_path = str(result.episode_path)
        details = result.error_summary or "No additional details"

        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return result.name
            if column == 1:
                return status_text
            if column == 2:
                return result.fonts_found
            if column == 3:
                return result.fonts_missing
            if column == 4:
                return result.error_summary or ""

        if role == Qt.ItemDataRole.ForegroundRole and column == 1:
            return QColor(status_color(result.status.value))

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column in (1, 2, 3):
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 0:
                return full_path
            if column == 1:
                return f"Episode status: {status_text}"
            if column == 2:
                return f"Fonts found: {result.fonts_found}"
            if column == 3:
                return f"Fonts missing: {result.fonts_missing}"
            return details

        if role == Qt.ItemDataRole.AccessibleTextRole:
            if column == 0:
                return f"Episode: {result.name}"
            if column == 1:
                return f"Status: {status_text}"
            if column == 2:
                return f"Fonts found: {result.fonts_found}"
            if column == 3:
                return f"Fonts missing: {result.fonts_missing}"
            return f"Details: {details}"

        if role == Qt.ItemDataRole.AccessibleDescriptionRole:
            return full_path if column == 0 else details

        return None

    @staticmethod
    def _status_text(status: EpisodeStatus) -> str:
        if status == EpisodeStatus.COMPLETE:
            return "✓ Complete"
        if status == EpisodeStatus.PARTIAL:
            return "⚠ Partial"
        if status == EpisodeStatus.FAILED:
            return "✕ Failed"
        return "— Skipped"

    def add_result(self, result: EpisodeResult) -> None:
        """Add a single episode result."""
        row = len(self.results)
        self.beginInsertRows(QModelIndex(), row, row)
        self.results.append(result)
        self.endInsertRows()

    def set_results(self, results: list[EpisodeResult]) -> None:
        """Set or overwrite the entire results list."""
        self.beginResetModel()
        self.results = list(results)
        self.endResetModel()

    def clear(self) -> None:
        """Clear all results in the model."""
        self.beginResetModel()
        self.results.clear()
        self.endResetModel()


class ResultsTableWidget(QWidget):
    """Results table with full-path tooltips and accessible outcome labels."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Pipeline results")
        self.setAccessibleDescription(
            "Episode pipeline results, including fonts found, missing, and details."
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            TOKENS.spacing_8,
            TOKENS.spacing_8,
            TOKENS.spacing_8,
            TOKENS.spacing_8,
        )
        layout.setSpacing(TOKENS.spacing_8)

        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(TOKENS.spacing_8)
        self.title_label = QLabel("Pipeline Results", self)
        self.title_label.setProperty("role", "section-title")
        control_layout.addWidget(self.title_label)
        control_layout.addStretch()

        self.clear_button = QPushButton("Clear Results", self)
        self.clear_button.setProperty("role", "secondary")
        self.clear_button.setAccessibleName("Clear pipeline results")
        self.clear_button.setAccessibleDescription(
            "Remove rows currently displayed in the pipeline results table."
        )
        self.clear_button.setToolTip("Clear the results table")
        self.clear_button.clicked.connect(self.clear_results)
        control_layout.addWidget(self.clear_button)
        layout.addLayout(control_layout)

        self.table_view = QTableView(self)
        self.table_view.setAccessibleName("Pipeline result rows")
        self.table_view.setAccessibleDescription(
            "Read-only episode outcomes. Use arrow keys to review full-path tooltips."
        )
        self.table_view.setToolTip("Pipeline results by episode")
        self.table_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table_view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setShowGrid(False)
        self.table_view.verticalHeader().setDefaultSectionSize(TOKENS.table_row_height)

        self.model = ResultsTableModel()
        self.table_view.setModel(self.model)

        header = self.table_view.horizontalHeader()
        header.setAccessibleName("Pipeline result columns")
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table_view.setColumnWidth(0, 300)

        layout.addWidget(self.table_view)
        QWidget.setTabOrder(self.table_view, self.clear_button)
        logger.info("ResultsTableWidget initialized with virtual model QTableView")

    def add_episode_result(self, result: EpisodeResult) -> None:
        """Append one episode result and reveal the table when it has output."""
        self.model.add_result(result)
        self.setVisible(True)

    def populate(self, run_result: PipelineRunResult) -> None:
        """Populate the table with the results from a pipeline run."""
        self.model.set_results(run_result.episodes)
        self.setVisible(True)

    def clear_results(self) -> None:
        """Clear all rows in the results table."""
        self.model.clear()
        logger.info("Results table cleared")
