"""Centralized visual tokens and application styling for Anime Studio."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


@dataclass(frozen=True)
class DesignTokens:
    """Semantic desktop design tokens shared by all PySide6 surfaces."""

    background: str = "#0F172A"
    surface: str = "#162033"
    surface_elevated: str = "#1E293B"
    surface_hover: str = "#26364D"
    border: str = "#334155"
    border_strong: str = "#475569"
    text_primary: str = "#F8FAFC"
    text_secondary: str = "#CBD5E1"
    text_muted: str = "#94A3B8"
    accent: str = "#3B82F6"
    accent_hover: str = "#60A5FA"
    accent_pressed: str = "#2563EB"
    success: str = "#22C55E"
    warning: str = "#F59E0B"
    danger: str = "#EF4444"
    danger_hover: str = "#F87171"
    stopped: str = "#64748B"
    focus: str = "#93C5FD"
    disabled_background: str = "#1E293B"
    disabled_text: str = "#94A3B8"
    text_on_accent: str = "#FFFFFF"
    activity_timestamp: str = "#94A3B8"
    activity_debug: str = "#94A3B8"
    spacing_4: int = 4
    spacing_8: int = 8
    spacing_12: int = 12
    spacing_16: int = 16
    spacing_24: int = 24
    spacing_32: int = 32
    radius_small: int = 4
    radius_medium: int = 8
    radius_large: int = 12
    control_height: int = 32
    primary_control_height: int = 36
    header_height: int = 44
    sidebar_width: int = 220
    table_row_height: int = 36
    status_column_width: int = 104
    select_column_width: int = 64
    activity_collapsed_height: int = 36
    activity_expanded_max_height: int = 160


TOKENS: Final = DesignTokens()

_STATUS_ALIASES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "all_done": "complete",
        "complete": "complete",
        "muxed": "complete",
        "success": "complete",
        "pending": "pending",
        "ready": "ready",
        "partial": "partial",
        "warning": "warning",
        "no_subtitle": "warning",
        "skipped": "skipped",
        "stopped": "stopped",
        "processing": "processing",
        "error": "failed",
        "failed": "failed",
        "failure": "failed",
    }
)

_STATUS_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "complete": "Complete",
        "pending": "Pending",
        "ready": "Ready",
        "partial": "Partial",
        "warning": "Warning",
        "skipped": "Skipped",
        "stopped": "Stopped",
        "processing": "Processing",
        "failed": "Failed",
        "unknown": "Unknown",
    }
)


def canonical_status(status: str) -> str:
    """Return the canonical presentation status for a domain/UI status value."""

    return _STATUS_ALIASES.get(status.strip().casefold(), "unknown")


def status_label(status: str) -> str:
    """Return readable status text so status is never conveyed by color alone."""

    return _STATUS_LABELS[canonical_status(status)]


def status_color(status: str) -> str:
    """Return the semantic color assigned to a status value."""

    canonical = canonical_status(status)
    if canonical == "complete":
        return TOKENS.success
    if canonical in {"pending", "ready", "partial", "warning"}:
        return TOKENS.warning
    if canonical in {"skipped", "stopped", "unknown"}:
        return TOKENS.stopped
    if canonical == "processing":
        return TOKENS.accent
    return TOKENS.danger


def refresh_widget_style(widget: QWidget) -> None:
    """Reapply QSS after a dynamic widget property changes."""

    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def application_stylesheet() -> str:
    """Return the restrained, high-contrast desktop stylesheet from tokens."""

    return f"""
        QWidget {{
            background-color: {TOKENS.background};
            color: {TOKENS.text_primary};
            font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
            font-size: 13px;
        }}

        QMainWindow {{
            background-color: {TOKENS.background};
        }}

        QLabel[role="app-title"] {{
            color: {TOKENS.text_primary};
            font-size: 18px;
            font-weight: 700;
        }}

        QLabel[role="show-title"] {{
            color: {TOKENS.text_primary};
            font-size: 20px;
            font-weight: 700;
        }}

        QLabel[role="section-title"] {{
            color: {TOKENS.text_primary};
            font-size: 14px;
            font-weight: 600;
        }}

        QLabel[role="secondary"] {{
            color: {TOKENS.text_secondary};
        }}

        QLabel[role="muted"] {{
            color: {TOKENS.text_muted};
        }}

        QPushButton {{
            min-height: {TOKENS.control_height}px;
            padding: 0 {TOKENS.spacing_12}px;
            border: 1px solid {TOKENS.border};
            border-radius: {TOKENS.radius_medium}px;
            background-color: {TOKENS.surface_elevated};
            color: {TOKENS.text_primary};
            font-weight: 600;
        }}

        QPushButton:hover {{
            background-color: {TOKENS.surface_hover};
            border-color: {TOKENS.border_strong};
        }}

        QPushButton:pressed {{
            background-color: {TOKENS.border};
        }}

        QPushButton:disabled {{
            background-color: {TOKENS.disabled_background};
            border-color: {TOKENS.border};
            color: {TOKENS.disabled_text};
        }}

        QPushButton[role="primary"] {{
            min-height: {TOKENS.primary_control_height}px;
            background-color: {TOKENS.accent};
            border-color: {TOKENS.accent};
            color: {TOKENS.text_on_accent};
        }}

        QPushButton[role="primary"]:hover {{
            background-color: {TOKENS.accent_hover};
            border-color: {TOKENS.accent_hover};
        }}

        QPushButton[role="primary"]:pressed {{
            background-color: {TOKENS.accent_pressed};
            border-color: {TOKENS.accent_pressed};
        }}

        QPushButton[role="danger"] {{
            background-color: {TOKENS.danger};
            border-color: {TOKENS.danger};
            color: {TOKENS.text_on_accent};
        }}

        QPushButton[role="danger"]:hover {{
            background-color: {TOKENS.danger_hover};
            border-color: {TOKENS.danger_hover};
        }}

        QToolButton {{
            min-height: {TOKENS.control_height}px;
            padding: 0 {TOKENS.spacing_8}px;
            border: 1px solid transparent;
            border-radius: {TOKENS.radius_medium}px;
            background-color: transparent;
            color: {TOKENS.text_primary};
            font-weight: 600;
        }}

        QToolButton:hover {{
            background-color: {TOKENS.surface_hover};
            border-color: {TOKENS.border};
        }}

        QToolButton:pressed {{
            background-color: {TOKENS.border};
        }}

        QPushButton:focus, QToolButton:focus, QListWidget:focus,
        QTableView:focus, QPlainTextEdit:focus, QComboBox:focus {{
            border: 2px solid {TOKENS.focus};
        }}

        QListWidget, QTableView, QPlainTextEdit, QComboBox {{
            background-color: {TOKENS.surface};
            border: 1px solid {TOKENS.border};
            border-radius: {TOKENS.radius_medium}px;
            color: {TOKENS.text_primary};
            selection-background-color: {TOKENS.accent};
            selection-color: {TOKENS.text_on_accent};
        }}

        QListWidget::item {{
            border-radius: {TOKENS.radius_small}px;
            padding: {TOKENS.spacing_8}px;
        }}

        QListWidget::item:hover {{
            background-color: {TOKENS.surface_hover};
        }}

        QListWidget::item:selected {{
            background-color: {TOKENS.accent};
            color: {TOKENS.text_on_accent};
        }}

        QHeaderView::section {{
            min-height: {TOKENS.control_height}px;
            padding: 0 {TOKENS.spacing_8}px;
            border: 0;
            border-bottom: 1px solid {TOKENS.border};
            background-color: {TOKENS.surface_elevated};
            color: {TOKENS.text_secondary};
            font-weight: 600;
        }}

        QProgressBar {{
            min-height: {TOKENS.control_height}px;
            border: 1px solid {TOKENS.border};
            border-radius: {TOKENS.radius_medium}px;
            background-color: {TOKENS.surface};
            color: {TOKENS.text_primary};
            text-align: center;
        }}

        QProgressBar::chunk {{
            border-radius: {TOKENS.radius_small}px;
            background-color: {TOKENS.accent};
        }}

        QProgressBar[progressState="success"] {{ border-color: {TOKENS.success}; }}
        QProgressBar[progressState="success"]::chunk {{ background-color: {TOKENS.success}; }}
        QProgressBar[progressState="error"] {{ border-color: {TOKENS.danger}; }}
        QProgressBar[progressState="error"]::chunk {{ background-color: {TOKENS.danger}; }}
        QProgressBar[progressState="stopped"] {{ border-color: {TOKENS.stopped}; }}
        QProgressBar[progressState="stopped"]::chunk {{ background-color: {TOKENS.stopped}; }}

        QScrollBar:vertical {{
            width: {TOKENS.spacing_12}px;
            background: {TOKENS.surface};
            margin: {TOKENS.spacing_4}px;
        }}

        QScrollBar::handle:vertical {{
            min-height: {TOKENS.spacing_24}px;
            border-radius: {TOKENS.radius_small}px;
            background: {TOKENS.border_strong};
        }}

        QScrollBar::handle:vertical:hover {{
            background: {TOKENS.text_muted};
        }}
    """


def apply_dark_theme(app: QApplication) -> None:
    """Apply the project-owned dark desktop palette and semantic QSS."""

    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(
        QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(TOKENS.background)
    )
    palette.setColor(
        QPalette.ColorGroup.All,
        QPalette.ColorRole.WindowText,
        QColor(TOKENS.text_primary),
    )
    palette.setColor(
        QPalette.ColorGroup.All, QPalette.ColorRole.Base, QColor(TOKENS.surface)
    )
    palette.setColor(
        QPalette.ColorGroup.All,
        QPalette.ColorRole.AlternateBase,
        QColor(TOKENS.surface_elevated),
    )
    palette.setColor(
        QPalette.ColorGroup.All,
        QPalette.ColorRole.ToolTipBase,
        QColor(TOKENS.surface_elevated),
    )
    palette.setColor(
        QPalette.ColorGroup.All,
        QPalette.ColorRole.ToolTipText,
        QColor(TOKENS.text_primary),
    )
    palette.setColor(
        QPalette.ColorGroup.All, QPalette.ColorRole.Text, QColor(TOKENS.text_primary)
    )
    palette.setColor(
        QPalette.ColorGroup.All,
        QPalette.ColorRole.Button,
        QColor(TOKENS.surface_elevated),
    )
    palette.setColor(
        QPalette.ColorGroup.All,
        QPalette.ColorRole.ButtonText,
        QColor(TOKENS.text_primary),
    )
    palette.setColor(
        QPalette.ColorGroup.All, QPalette.ColorRole.Link, QColor(TOKENS.accent)
    )
    palette.setColor(
        QPalette.ColorGroup.All,
        QPalette.ColorRole.Highlight,
        QColor(TOKENS.accent),
    )
    palette.setColor(
        QPalette.ColorGroup.All,
        QPalette.ColorRole.HighlightedText,
        QColor(TOKENS.text_on_accent),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(TOKENS.disabled_text),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(TOKENS.disabled_text),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(TOKENS.disabled_text),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Base,
        QColor(TOKENS.disabled_background),
    )

    app.setPalette(palette)
    app.setStyleSheet(application_stylesheet())
