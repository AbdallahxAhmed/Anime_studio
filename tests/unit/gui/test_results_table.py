import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from src.gui.messages import EpisodeResult, EpisodeStatus, PipelineRunResult
from src.gui.widgets.results_table import ResultsTableModel, ResultsTableWidget


@pytest.fixture(scope="session", autouse=True)
def q_app() -> QApplication:
    """Ensure a QApplication instance exists for GUI unit testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_results_model_initial_state() -> None:
    """Verify that ResultsTableModel starts empty with correct headers."""
    model = ResultsTableModel()
    assert model.rowCount() == 0
    assert model.columnCount() == 5
    assert model.headerData(0, Qt.Orientation.Horizontal) == "Episode"
    assert model.headerData(1, Qt.Orientation.Horizontal) == "Status"
    assert model.headerData(2, Qt.Orientation.Horizontal) == "Fonts Found"
    assert model.headerData(3, Qt.Orientation.Horizontal) == "Fonts Missing"
    assert model.headerData(4, Qt.Orientation.Horizontal) == "Details"


def test_results_model_data_roles() -> None:
    """Verify data roles output correct formatted values, colors, and alignments."""
    model = ResultsTableModel()
    result = EpisodeResult(
        name="Episode 01.mkv",
        status=EpisodeStatus.PARTIAL,
        fonts_found=3,
        fonts_missing=2,
        error_summary="OTS sanitize failed on font XYZ"
    )

    model.add_result(result)
    assert model.rowCount() == 1

    # 1. DisplayRole check
    idx_name = model.index(0, 0)
    idx_status = model.index(0, 1)
    idx_found = model.index(0, 2)
    idx_missing = model.index(0, 3)
    idx_details = model.index(0, 4)

    assert model.data(idx_name, Qt.ItemDataRole.DisplayRole) == "Episode 01.mkv"
    assert model.data(idx_status, Qt.ItemDataRole.DisplayRole) == "⚠ Partial"
    assert model.data(idx_found, Qt.ItemDataRole.DisplayRole) == 3
    assert model.data(idx_missing, Qt.ItemDataRole.DisplayRole) == 2
    assert model.data(idx_details, Qt.ItemDataRole.DisplayRole) == "OTS sanitize failed on font XYZ"

    # 2. ForegroundRole check (Orange for PARTIAL)
    assert model.data(idx_status, Qt.ItemDataRole.ForegroundRole) == QColor("#FF9800")
    assert model.data(idx_name, Qt.ItemDataRole.ForegroundRole) is None

    # 3. TextAlignmentRole check
    assert model.data(idx_status, Qt.ItemDataRole.TextAlignmentRole) == Qt.AlignmentFlag.AlignCenter
    assert model.data(idx_name, Qt.ItemDataRole.TextAlignmentRole) == (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # 4. ToolTipRole check
    assert model.data(idx_status, Qt.ItemDataRole.ToolTipRole) == "OTS sanitize failed on font XYZ"
    assert model.data(idx_details, Qt.ItemDataRole.ToolTipRole) == "OTS sanitize failed on font XYZ"


def test_results_model_clear_and_set() -> None:
    """Verify set_results and clear model operations."""
    model = ResultsTableModel()
    results = [
        EpisodeResult(name="Ep1", status=EpisodeStatus.COMPLETE, fonts_found=1, fonts_missing=0),
        EpisodeResult(name="Ep2", status=EpisodeStatus.FAILED, fonts_found=0, fonts_missing=3, error_summary="fail")
    ]

    model.set_results(results)
    assert model.rowCount() == 2

    model.clear()
    assert model.rowCount() == 0


def test_results_table_widget_populate_and_clear() -> None:
    """Verify ResultsTableWidget populates from PipelineRunResult and clears logs."""
    widget = ResultsTableWidget()
    
    episodes = [
        EpisodeResult(name="Ep1.mkv", status=EpisodeStatus.COMPLETE, fonts_found=4, fonts_missing=0)
    ]
    run_result = PipelineRunResult(
        episodes=episodes,
        total_duration_seconds=5.2,
        report_path="report.md",
        total_fonts_found=4,
        total_fonts_missing=0,
        dry_run=True
    )

    widget.populate(run_result)
    assert widget.model.rowCount() == 1

    # Simulate Clear Results button press
    widget.clear_button.click()
    assert widget.model.rowCount() == 0
