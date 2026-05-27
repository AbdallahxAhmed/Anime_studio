from PySide6.QtWidgets import QMessageBox, QWidget
from src.gui.messages import ErrorInfo


def show_error_dialog(parent: QWidget | None, error: ErrorInfo) -> None:
    """Display an ErrorInfo object as a native QMessageBox dialog.

    If the error is marked critical, it displays a Critical QMessageBox,
    otherwise it displays an Information QMessageBox. Detailed text is shown
    using Qt's expandable detailed text box if provided.
    """
    title = "Critical Error" if error.is_critical else "Information"
    icon = (
        QMessageBox.Icon.Critical if error.is_critical else QMessageBox.Icon.Information
    )

    box = QMessageBox(icon, title, error.message, parent=parent)

    if error.detail:
        box.setDetailedText(error.detail)

    box.exec()
