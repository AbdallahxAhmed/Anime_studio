import pytest
from src.gui.widgets.undo_dialog import UndoDialog
from src.models.run_manifest import RunManifest, EpisodeProcessed


@pytest.fixture
def q_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_undo_dialog_creation(q_app):
    dialog = UndoDialog()
    assert dialog.windowTitle() == "Undo Pipeline Operations"
    assert dialog.run_combo.count() == 0


def test_undo_dialog_populate_manifests(q_app):
    dialog = UndoDialog()

    ep = EpisodeProcessed(
        episode_path="/anime/Show A/ep1.mkv", show_name="Show A", status="success"
    )
    manifest = RunManifest(
        run_id="run-1",
        timestamp="2026-06-07 12:00:00",
        library_path="/anime",
        episodes_processed=(ep,),
    )

    dialog.populate([manifest])
    assert dialog.run_combo.count() == 1
    assert "Run 2026-06-07 12:00:00" in dialog.run_combo.itemText(0)
    assert "Show A" in dialog.info_label.text()


def test_undo_dialog_level_radio_buttons(q_app):
    dialog = UndoDialog()
    ep = EpisodeProcessed(
        episode_path="/anime/Show A/ep1.mkv", show_name="Show A", status="success"
    )
    manifest = RunManifest(
        run_id="run-1",
        timestamp="2026-06-07 12:00:00",
        library_path="/anime",
        episodes_processed=(ep,),
    )
    dialog.populate([manifest])
    dialog.show()

    # By default, entire run should be checked, lists hidden
    assert dialog.radio_entire.isChecked() is True
    assert dialog.show_list.isVisible() is False
    assert dialog.episode_combo.isVisible() is False

    # Toggle "by show"
    dialog.radio_show.setChecked(True)
    assert dialog.show_list.isVisible() is True
    assert dialog.show_list.count() == 1
    assert dialog.show_list.item(0).text() == "Show A"

    # Toggle "specific episode"
    dialog.radio_episode.setChecked(True)
    assert dialog.episode_combo.isVisible() is True
    assert dialog.episode_combo.count() == 1
    assert dialog.episode_combo.itemText(0) == "ep1.mkv"


def test_undo_dialog_signal_emission(q_app, mocker):
    dialog = UndoDialog()
    ep = EpisodeProcessed(
        episode_path="/anime/Show A/ep1.mkv", show_name="Show A", status="success"
    )
    manifest = RunManifest(
        run_id="run-1",
        timestamp="2026-06-07 12:00:00",
        library_path="/anime",
        episodes_processed=(ep,),
    )
    dialog.populate([manifest])

    spy = mocker.MagicMock()
    dialog.undo_requested.connect(spy)

    # Keep entire run selected
    dialog._on_accept()

    spy.assert_called_once_with({"manifest_index": 0, "level": "full"})
