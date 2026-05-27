import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QFileDialog
from src.gui.widgets.library_picker import LibraryPickerWidget


@pytest.fixture(scope="session", autouse=True)
def q_app() -> QApplication:
    """Ensure a QApplication instance exists for GUI unit testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_library_picker_initial_state() -> None:
    """Verify that LibraryPickerWidget starts with default state."""
    picker = LibraryPickerWidget()
    assert picker.get_path() == ""
    assert picker.path_display.isReadOnly() is True
    assert picker.path_display.placeholderText() == "No library path selected..."


def test_library_picker_set_valid_path(tmp_path: Path) -> None:
    """Verify set_path displays valid directories."""
    picker = LibraryPickerWidget()
    picker.set_path(tmp_path)
    assert picker.get_path() == str(tmp_path.resolve())


def test_library_picker_set_invalid_path(tmp_path: Path) -> None:
    """Verify set_path rejects invalid files or directories."""
    picker = LibraryPickerWidget()
    fake_file = tmp_path / "not_a_dir.txt"
    fake_file.write_text("hello", encoding="utf-8")

    picker.set_path(fake_file)
    assert picker.get_path() == ""


def test_library_picker_browse_select_folder(mocker, tmp_path: Path) -> None:
    """Verify browse dialog selection emits signal and updates field."""
    picker = LibraryPickerWidget()
    selected_path = tmp_path / "anime_library"
    selected_path.mkdir()

    # Mock QFileDialog.getExistingDirectory to return our path
    mocker.patch.object(
        QFileDialog,
        "getExistingDirectory",
        return_value=str(selected_path.resolve())
    )

    # Listen to library_selected signal
    emitted = []
    picker.library_selected.connect(emitted.append)

    # Trigger browse click
    picker.browse_button.click()

    assert picker.get_path() == str(selected_path.resolve())
    assert len(emitted) == 1
    assert emitted[0] == str(selected_path.resolve())


def test_library_picker_browse_cancel(mocker) -> None:
    """Verify canceling the browse dialog does not alter path or emit."""
    picker = LibraryPickerWidget()
    
    # Mock QFileDialog.getExistingDirectory to return empty string
    mocker.patch.object(
        QFileDialog,
        "getExistingDirectory",
        return_value=""
    )

    emitted = []
    picker.library_selected.connect(emitted.append)

    picker.browse_button.click()

    assert picker.get_path() == ""
    assert len(emitted) == 0
