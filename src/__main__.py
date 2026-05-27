import asyncio
import sys
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from src.gui.bootstrap import bootstrap_app
from src.gui.theme import apply_dark_theme


def main() -> None:
    """Entry point to launch the PySide6 GUI application with qasync."""
    app = QApplication(sys.argv)

    # Set up qasync as the active asyncio event loop
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Apply the dark theme (with Fusion fallback)
    apply_dark_theme(app)

    # Bootstrap the application composition root
    window = bootstrap_app(app)
    window.show()

    # Run the loop forever until the application exits
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
