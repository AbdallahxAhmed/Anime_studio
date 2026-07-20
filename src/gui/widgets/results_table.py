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

logger = logging.getLogger("anime_studio.gui.widgets.results_table")


class ResultsTableModel(QAbstractTableModel):
    """Memory-efficient custom table model for displaying pipeline episode outcomes."""

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
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return result.name
            elif col == 1:
                if result.status == EpisodeStatus.COMPLETE:
                    return "✓ Success"
                elif result.status == EpisodeStatus.PARTIAL:
                    return "⚠ Partial"
                elif result.status == EpisodeStatus.FAILED:
                    return "✗ Failed"
                else:  # SKIPPED
                    return "⤼ Skipped"
            elif col == 2:
                return result.fonts_found
            elif col == 3:
                return result.fonts_missing
            elif col == 4:
                return result.error_summary or ""

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 1:
                # Color code status column
                if result.status == EpisodeStatus.COMPLETE:
                    return QColor("#4CAF50")  # Green
                elif result.status == EpisodeStatus.PARTIAL:
                    return QColor("#FF9800")  # Orange
                elif result.status == EpisodeStatus.FAILED:
                    return QColor("#F44336")  # Red
                else:
                    return QColor("#9E9E9E")  # Gray

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (1, 2, 3):
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == 4 or col == 1:
                return result.error_summary

        return None

    def add_result(self, result: EpisodeResult) -> None:
        """Add a single EpisodeResult to the model thread-safely."""
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
    """Table widget utilizing QTableView and virtual ResultsTableModel.

    Provides headers, auto-stretching for descriptions, and a Clear button.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Header Control Row
        control_layout = QHBoxLayout()
        self.title_label = QLabel("Pipeline Results", self)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        control_layout.addWidget(self.title_label)

        control_layout.addStretch()

        self.clear_button = QPushButton("Clear Results", self)
        self.clear_button.clicked.connect(self.clear_results)
        control_layout.addWidget(self.clear_button)

        layout.addLayout(control_layout)

        # Table View Configuration
        self.table_view = QTableView(self)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setAlternatingRowColors(True)

        # Instantiate Virtual Model
        self.model = ResultsTableModel()
        self.table_view.setModel(self.model)

        # Column stretching behavior
        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        # Default Column Widths
        self.table_view.setColumnWidth(0, 300)

        layout.addWidget(self.table_view)
        logger.info("ResultsTableWidget initialized with virtual model QTableView")

    def add_episode_result(self, result: EpisodeResult) -> None:
        """Append a single episode result to the table."""
        self.model.add_result(result)

    def populate(self, run_result: PipelineRunResult) -> None:
        """Populate the table with the episodes list from a PipelineRunResult."""
        if isinstance(run_result, PipelineRunResult):
            self.model.set_results(run_result.episodes)
        else:
            logger.warning(f"Invalid populate format: {type(run_result)}")  # type: ignore[unreachable]  # runtime fallback for untyped callers

    def clear_results(self) -> None:
        """Clear all rows in the results table."""
        self.model.clear()
        logger.info("Results table cleared")
