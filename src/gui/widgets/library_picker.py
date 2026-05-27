import logging
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

logger = logging.getLogger("anime_studio.gui.widgets.library_picker")


class LibraryPickerWidget(QWidget):
    """Widget allowing users to select an anime library folder.

    Provides a read-only path display line edit and a native QFileDialog browser button.
    Emits library_selected(str) signal when a valid folder is selected.
    """

    library_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        self.label = QLabel("Anime Library:", self)
        layout.addWidget(self.label)

        self.path_display = QLineEdit(self)
        self.path_display.setReadOnly(True)
        self.path_display.setPlaceholderText("No library path selected...")
        layout.addWidget(self.path_display)

        self.browse_button = QPushButton("Browse...", self)
        self.browse_button.clicked.connect(self._on_browse_clicked)
        layout.addWidget(self.browse_button)

    def set_path(self, path: str | Path | None) -> None:
        """Set the path in the text field and update the UI display."""
        if not path:
            self.path_display.clear()
            return

        p = Path(path)
        # Fast non-blocking check
        if p.is_dir():
            path_str = str(p.resolve())
            self.path_display.setText(path_str)
            logger.info(f"Library path display updated: {path_str}")
        else:
            logger.warning(f"Attempted to set invalid directory path: {p}")

    def get_path(self) -> str:
        """Get the currently displayed library path."""
        return self.path_display.text()

    def _on_browse_clicked(self) -> None:
        """Trigger native directory selection dialog."""
        current_dir = self.path_display.text() or ""
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Anime Library Directory",
            current_dir,
            QFileDialog.Option.ShowDirsOnly,
        )
        if selected_dir:
            p = Path(selected_dir)
            if p.is_dir():
                path_str = str(p.resolve())
                self.path_display.setText(path_str)
                self.library_selected.emit(path_str)
                logger.info(f"Directory selected: {path_str}")
