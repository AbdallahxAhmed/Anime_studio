"""Regression coverage for the project-owned desktop design system."""

from src.gui.theme import (
    TOKENS,
    application_stylesheet,
    canonical_status,
    status_color,
    status_label,
)


def _relative_luminance(color: str) -> float:
    channels = tuple(int(color[index : index + 2], 16) / 255 for index in (1, 3, 5))

    def linear(channel: float) -> float:
        return (
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(foreground: str, background: str) -> float:
    light, dark = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


def test_design_tokens_use_the_eight_point_spacing_scale() -> None:
    assert (
        TOKENS.spacing_8,
        TOKENS.spacing_16,
        TOKENS.spacing_24,
        TOKENS.spacing_32,
    ) == (
        8,
        16,
        24,
        32,
    )
    assert TOKENS.control_height == 32
    assert TOKENS.primary_control_height == 36
    assert TOKENS.sidebar_width == 220


def test_design_tokens_meet_readable_text_contrast_targets() -> None:
    assert _contrast_ratio(TOKENS.text_primary, TOKENS.background) >= 7.0
    assert _contrast_ratio(TOKENS.text_secondary, TOKENS.background) >= 4.5
    assert _contrast_ratio(TOKENS.disabled_text, TOKENS.disabled_background) >= 4.5


def test_status_presentation_is_textual_and_semantic() -> None:
    assert canonical_status("muxed") == "complete"
    assert canonical_status("error") == "failed"
    assert canonical_status("stopped") == "stopped"
    assert status_label("stopped") == "Stopped"
    assert status_color("complete") == TOKENS.success
    assert status_color("failed") == TOKENS.danger
    assert status_color("stopped") == TOKENS.stopped


def test_stylesheet_covers_focus_and_interaction_states() -> None:
    stylesheet = application_stylesheet()
    assert "QPushButton:hover" in stylesheet
    assert "QPushButton:pressed" in stylesheet
    assert "QPushButton:disabled" in stylesheet
    assert "QPushButton:focus" in stylesheet
    assert 'QProgressBar[progressState="stopped"]' in stylesheet
