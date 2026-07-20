from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
)
from src.models.pipeline import ShowNode


class SelectionTreeWidget(QWidget):
    """
    Shows the anime library as a hierarchical tree with checkboxes.
    Top level = shows (ShowNode). Second level = sub-folders (SubFolderNode).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        # Buttons
        self._select_all_btn = QPushButton("Select All")
        self._deselect_all_btn = QPushButton("Deselect All")

        # Layout
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self._select_all_btn)
        btn_layout.addWidget(self._deselect_all_btn)
        btn_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(btn_layout)
        layout.addWidget(self._tree)

        # Signals
        self._select_all_btn.clicked.connect(self._on_select_all)
        self._deselect_all_btn.clicked.connect(self._on_deselect_all)

    def populate(self, show_tree: tuple[ShowNode, ...]) -> None:
        """Build tree from ShowNode list. All checked by default."""
        self._tree.blockSignals(True)
        self._tree.clear()

        # Handle empty tree placeholder
        if not show_tree:
            item = QTreeWidgetItem(self._tree)
            item.setText(0, "No shows found")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self._tree.expandAll()
            self._tree.blockSignals(False)
            return

        for show in show_tree:
            show_item = QTreeWidgetItem(self._tree)
            show_item.setText(0, f"{show.name} ({show.total_count} episodes)")
            show_item.setData(0, Qt.ItemDataRole.UserRole, show.path)
            show_item.setFlags(
                show_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )

            # Handle shows with zero episodes - display but unchecked by default
            if show.total_count == 0:
                show_item.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                show_item.setCheckState(0, Qt.CheckState.Checked)

            for sf in show.sub_folders:
                sf_item = QTreeWidgetItem(show_item)
                sf_item.setText(0, f"{sf.name} ({sf.total_count} episodes)")
                sf_item.setData(0, Qt.ItemDataRole.UserRole, sf.path)
                sf_item.setFlags(
                    sf_item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsAutoTristate
                )
                if sf.total_count == 0:
                    sf_item.setCheckState(0, Qt.CheckState.Unchecked)
                else:
                    sf_item.setCheckState(0, Qt.CheckState.Checked)

        self._tree.expandAll()
        self._tree.blockSignals(False)

    def get_selected_paths(self) -> frozenset[Path]:
        """
        Returns frozenset of folder Paths that are fully or partially checked.
        Only returns LEAF paths (sub-folder paths if sub-folders exist,
        or show path if show has no sub-folders).
        """
        selected: set[Path] = set()
        root = self._tree.invisibleRootItem()

        for i in range(root.childCount()):
            show_item = root.child(i)
            raw_path = show_item.data(0, Qt.ItemDataRole.UserRole)
            if not raw_path:
                continue
            show_path = Path(raw_path)

            if show_item.childCount() == 0:
                # No sub-folders — show is leaf
                if show_item.checkState(0) != Qt.CheckState.Unchecked:
                    selected.add(show_path)
            else:
                # Has sub-folders — collect checked sub-folders
                for j in range(show_item.childCount()):
                    sf_item = show_item.child(j)
                    if sf_item.checkState(0) != Qt.CheckState.Unchecked:
                        raw_sf_path = sf_item.data(0, Qt.ItemDataRole.UserRole)
                        if raw_sf_path:
                            selected.add(Path(raw_sf_path))

        return frozenset(selected)

    def is_all_selected(self) -> bool:
        """True if everything is checked (Run All mode)."""
        return self.get_selected_paths() == self._all_paths()

    def _all_paths(self) -> frozenset[Path]:
        # Helper: all leaf paths
        all_paths: set[Path] = set()
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            show_item = root.child(i)
            raw_path = show_item.data(0, Qt.ItemDataRole.UserRole)
            if not raw_path:
                continue
            show_path = Path(raw_path)

            if show_item.childCount() == 0:
                all_paths.add(show_path)
            else:
                for j in range(show_item.childCount()):
                    sf_item = show_item.child(j)
                    raw_sf_path = sf_item.data(0, Qt.ItemDataRole.UserRole)
                    if raw_sf_path:
                        all_paths.add(Path(raw_sf_path))
        return frozenset(all_paths)

    def _on_select_all(self) -> None:
        self._set_all_checked(Qt.CheckState.Checked)

    def _on_deselect_all(self) -> None:
        self._set_all_checked(Qt.CheckState.Unchecked)

    def _set_all_checked(self, state: Qt.CheckState) -> None:
        self._tree.blockSignals(True)
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            show_item = root.child(i)
            show_item.setCheckState(0, state)
            # ItemIsAutoTristate propagates to children automatically
            # But in PySide6 blockSignals(True) might prevent standard Qt propagation, so let's explicitly set children state too.
            for j in range(show_item.childCount()):
                show_item.child(j).setCheckState(0, state)
        self._tree.blockSignals(False)
