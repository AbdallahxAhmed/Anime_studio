from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static, Button


class ErrorModal(ModalScreen[None]):
    """Modal dialog displaying fatal system or setup errors with helpful suggestions."""

    def __init__(
        self, title: str, message: str, suggestion: str = "", **kwargs
    ) -> None:
        self.error_title = title
        self.error_message = message
        self.error_suggestion = suggestion
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Vertical(id="error-modal-container"):
            yield Label(self.error_title, id="error-title")
            yield Static(self.error_message, id="error-message")
            if self.error_suggestion:
                yield Static(self.error_suggestion, id="error-suggestion")
            yield Button("Dismiss", id="dismiss-button", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dismiss-button":
            self.dismiss()
