from typing import Any, TYPE_CHECKING
from pathlib import Path
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QComboBox,
    QGroupBox,
    QRadioButton,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QWidget,
)

if TYPE_CHECKING:
    from src.models.run_manifest import RunManifest


class UndoDialog(QDialog):
    """Dialog to choose a run and configure an undo operation."""

    # Emits a dict: {
    #   "manifest_index": int,
    #   "level": "full" | "show" | "episode",
    #   "show_names": list[str],     # populated if level is "show"
    #   "episode_names": list[str]    # populated if level is "episode"
    # }
    undo_requested = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Undo Pipeline Operations")
        self.resize(500, 450)
        self.setMinimumSize(400, 350)

        self.manifests: list[RunManifest] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 1. Run Selector
        run_group = QGroupBox("Select Pipeline Run", self)
        run_layout = QVBoxLayout(run_group)
        self.run_combo = QComboBox(run_group)
        self.run_combo.currentIndexChanged.connect(self._on_run_selected)
        run_layout.addWidget(self.run_combo)

        self.info_label = QLabel("", run_group)
        self.info_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        run_layout.addWidget(self.info_label)
        layout.addWidget(run_group)

        # 2. Undo Level Selector
        level_group = QGroupBox("Undo Range", self)
        level_layout = QVBoxLayout(level_group)

        self.radio_entire = QRadioButton("Entire Run", level_group)
        self.radio_entire.setChecked(True)
        self.radio_entire.toggled.connect(self._on_level_changed)
        level_layout.addWidget(self.radio_entire)

        self.radio_show = QRadioButton("By Show", level_group)
        self.radio_show.toggled.connect(self._on_level_changed)
        level_layout.addWidget(self.radio_show)

        # Checklist for "by show"
        self.show_list = QListWidget(level_group)
        self.show_list.setVisible(False)
        self.show_list.setStyleSheet(
            "QListWidget { background: #f8f9fa; border: 1px solid #ced4da; border-radius: 4px; }"
        )
        level_layout.addWidget(self.show_list)

        self.radio_episode = QRadioButton("Specific Episode", level_group)
        self.radio_episode.toggled.connect(self._on_level_changed)
        level_layout.addWidget(self.radio_episode)

        # Dropdown for "specific episode"
        self.episode_combo = QComboBox(level_group)
        self.episode_combo.setVisible(False)
        level_layout.addWidget(self.episode_combo)

        layout.addWidget(level_group)

        # 3. Warning label (30-day trash warning)
        self.warning_label = QLabel(
            "⚠️ Warning: Restoring is performed from the trash. Items in trash folder for "
            "longer than 30 days might be permanently purged.",
            self,
        )
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(
            "color: #d9534f; font-weight: bold; font-size: 11px;"
        )
        layout.addWidget(self.warning_label)

        # 4. Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        self.undo_btn = QPushButton("Undo Selected", self)
        self.undo_btn.setDefault(True)
        self.button_box.addButton(self.undo_btn, QDialogButtonBox.ButtonRole.AcceptRole)

        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def populate(self, manifests: list["RunManifest"]) -> None:
        """Populate the run selector with historical runs."""
        self.manifests = manifests
        self.run_combo.clear()

        for idx, m in enumerate(manifests):
            # Format date/time
            success_count = m.success_count
            label = f"Run {m.timestamp} ({success_count} success)"
            self.run_combo.addItem(label)

        if manifests:
            self.run_combo.setCurrentIndex(0)
            self._on_run_selected(0)
        else:
            self.info_label.setText("No run history available.")

    def _on_run_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.manifests):
            return
        m = self.manifests[index]
        self.info_label.setText(
            f"Library: {m.library_path}\nShows: {', '.join(m.show_names) or 'None'}"
        )
        self._update_details()

    def _on_level_changed(self) -> None:
        self._update_details()

    def _update_details(self) -> None:
        idx = self.run_combo.currentIndex()
        if idx < 0 or idx >= len(self.manifests):
            self.show_list.setVisible(False)
            self.episode_combo.setVisible(False)
            return

        m = self.manifests[idx]

        if self.radio_entire.isChecked():
            self.show_list.setVisible(False)
            self.episode_combo.setVisible(False)
        elif self.radio_show.isChecked():
            self.show_list.setVisible(True)
            self.episode_combo.setVisible(False)

            # Populate show list as checkable items
            self.show_list.clear()
            for show in m.show_names:
                item = QListWidgetItem(show)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.show_list.addItem(item)
        elif self.radio_episode.isChecked():
            self.show_list.setVisible(False)
            self.episode_combo.setVisible(True)

            # Populate episode combo
            self.episode_combo.clear()
            for ep in m.episodes_processed:
                if ep.status == "success":
                    # Display filename
                    filename = Path(ep.episode_path).name
                    self.episode_combo.addItem(filename, ep.episode_path)

    def _on_accept(self) -> None:
        idx = self.run_combo.currentIndex()
        if idx < 0 or idx >= len(self.manifests):
            self.reject()
            return

        payload: dict[str, Any] = {
            "manifest_index": idx,
        }

        if self.radio_entire.isChecked():
            payload["level"] = "full"
        elif self.radio_show.isChecked():
            payload["level"] = "show"
            # Gather checked shows
            shows = []
            for i in range(self.show_list.count()):
                item = self.show_list.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    shows.append(item.text())
            payload["show_names"] = shows
        elif self.radio_episode.isChecked():
            payload["level"] = "episode"
            self.episode_combo.currentData()
            # We pass filename and the list of episode paths to match main_window's expected payload
            ep_name = self.episode_combo.currentText()
            payload["episode_names"] = [ep_name] if ep_name else []

        self.undo_requested.emit(payload)
        self.accept()
