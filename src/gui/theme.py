import logging
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

logger = logging.getLogger("anime_studio.gui.theme")


def apply_dark_theme(app: QApplication) -> None:
    """Apply a modern dark theme to the application.

    Tries to load qdarktheme first. If qdarktheme fails or is unavailable,
    it falls back to the Fusion style with a customized dark QPalette.
    """
    try:
        import qdarktheme

        theme = qdarktheme.load_theme("dark")
        app.setStyleSheet(theme)
        logger.info("Successfully applied qdarktheme (dark mode)")
    except Exception as e:
        logger.warning(
            "qdarktheme failed to load, falling back to Fusion dark palette", exc_info=e
        )
        app.setStyle("Fusion")

        palette = QPalette()
        # Base colors
        palette.setColor(
            QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(53, 53, 53)
        )
        palette.setColor(
            QPalette.ColorGroup.All,
            QPalette.ColorRole.WindowText,
            QColor(220, 220, 220),
        )
        palette.setColor(
            QPalette.ColorGroup.All, QPalette.ColorRole.Base, QColor(30, 30, 30)
        )
        palette.setColor(
            QPalette.ColorGroup.All,
            QPalette.ColorRole.AlternateBase,
            QColor(45, 45, 45),
        )
        palette.setColor(
            QPalette.ColorGroup.All,
            QPalette.ColorRole.ToolTipBase,
            QColor(255, 255, 255),
        )
        palette.setColor(
            QPalette.ColorGroup.All,
            QPalette.ColorRole.ToolTipText,
            QColor(220, 220, 220),
        )
        palette.setColor(
            QPalette.ColorGroup.All, QPalette.ColorRole.Text, QColor(220, 220, 220)
        )
        palette.setColor(
            QPalette.ColorGroup.All, QPalette.ColorRole.Button, QColor(53, 53, 53)
        )
        palette.setColor(
            QPalette.ColorGroup.All,
            QPalette.ColorRole.ButtonText,
            QColor(220, 220, 220),
        )
        palette.setColor(
            QPalette.ColorGroup.All, QPalette.ColorRole.BrightText, QColor(255, 0, 0)
        )
        palette.setColor(
            QPalette.ColorGroup.All, QPalette.ColorRole.Link, QColor(42, 130, 218)
        )
        palette.setColor(
            QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, QColor(42, 130, 218)
        )
        palette.setColor(
            QPalette.ColorGroup.All,
            QPalette.ColorRole.HighlightedText,
            QColor(255, 255, 255),
        )

        # Disabled state colors
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.WindowText,
            QColor(127, 127, 127),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127)
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            QColor(127, 127, 127),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(40, 40, 40)
        )

        app.setPalette(palette)
