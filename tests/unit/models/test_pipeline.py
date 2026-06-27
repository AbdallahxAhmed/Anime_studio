from pathlib import Path
import pytest
from src.models.pipeline import ShowStatus, ShowSummary


def test_show_status_values() -> None:
    """Test all 6 ShowStatus values exist and are strings."""
    expected_values = {
        "pending",
        "processing",
        "ready",
        "all_done",
        "no_subtitle",
        "warning",
    }
    # Check that they exist
    assert len(ShowStatus) == 6
    actual_values = {status.value for status in ShowStatus}
    assert actual_values == expected_values

    # Check they are strings
    for status in ShowStatus:
        assert isinstance(status, str)
        assert isinstance(status.value, str)


def test_show_summary_creation_and_immutability() -> None:
    """Test ShowSummary creation, frozen immutability, and absolute path check."""
    path = Path("D:/Entertainment/Anime/Wistoria").absolute()
    summary = ShowSummary(
        name="Wistoria",
        path=path,
        status=ShowStatus.READY,
        episode_count=12,
        processed_count=2,
        subtitle_text="2 processed / 10 pending",
    )

    # Creation verification
    assert summary.name == "Wistoria"
    assert summary.path == path
    assert summary.path.is_absolute()
    assert summary.status == ShowStatus.READY
    assert summary.episode_count == 12
    assert summary.processed_count == 2
    assert summary.subtitle_text == "2 processed / 10 pending"

    # Frozen enforcement
    with pytest.raises(AttributeError):
        # Frozen dataclass should raise AttributeError on modification
        summary.status = ShowStatus.ALL_DONE  # type: ignore[misc]


def test_show_summary_subtitle_text_accepts_any_string() -> None:
    """Test that ShowSummary subtitle_text field accepts any string format."""
    path = Path("D:/Entertainment/Anime/Wistoria").absolute()
    
    test_strings = [
        "",
        "Any random string text",
        "12 ready / 2 processed",
        "No subtitle files found!",
        "Special characters: !@#$%^&*()_+",
    ]
    
    for subtitle_str in test_strings:
        summary = ShowSummary(
            name="Wistoria",
            path=path,
            status=ShowStatus.READY,
            episode_count=12,
            processed_count=2,
            subtitle_text=subtitle_str,
        )
        assert summary.subtitle_text == subtitle_str
