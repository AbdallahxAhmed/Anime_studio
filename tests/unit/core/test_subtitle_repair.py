import pytest
from pathlib import Path
from src.core.subtitle_repair import extract_fonts, repair_ass, _normalize_font_name
from src.models.font import FontQuery
from src.errors import EncodingRepairError

FIXTURE_DIR = Path("tests/fixtures/ass_samples")

def test_normalize_font_name():
    # Test stripping vertical prefix @
    assert _normalize_font_name("@Arial") == "Arial"
    assert _normalize_font_name("  @Arial  ") == "Arial"
    
    # Test stripping common weight suffixes
    assert _normalize_font_name("Arial Bold") == "Arial"
    assert _normalize_font_name("Arial Italic") == "Arial"
    assert _normalize_font_name("Arial Bold Italic") == "Arial"
    assert _normalize_font_name("Arial Regular") == "Arial"
    assert _normalize_font_name("Arial SemiBold") == "Arial"
    assert _normalize_font_name("Arial ExtraBold") == "Arial"
    assert _normalize_font_name("Arial Light") == "Arial"
    assert _normalize_font_name("Arial Medium") == "Arial"
    assert _normalize_font_name("Arial Thin") == "Arial"
    assert _normalize_font_name("Arial Black") == "Arial"
    assert _normalize_font_name("Arial Heavy") == "Arial"
    
    # Test preserving Noto Sans CJK JP
    assert _normalize_font_name("Noto Sans CJK JP") == "Noto Sans CJK JP"
    assert _normalize_font_name("Noto Sans CJK JP Bold") == "Noto Sans CJK JP"

def test_extract_fonts_valid():
    # Parse from valid 3-style file
    content = FIXTURE_DIR.joinpath("valid_3_style.ass").read_text(encoding="utf-8")
    queries = extract_fonts(
        content=content,
        episode_path=Path("ep1.mkv"),
        anime_title="Naruto"
    )
    
    assert len(queries) == 3
    assert all(isinstance(q, FontQuery) for q in queries)
    
    # Sort and verify requested names
    names = sorted([q.requested_name for q in queries])
    assert names == ["Arial", "Comic Sans MS", "Noto Sans"]
    assert all(q.anime_title == "Naruto" for q in queries)
    assert all(q.episode_path == Path("ep1.mkv") for q in queries)

def test_extract_fonts_deduplication():
    # Construct content with duplicates
    content = """[V4+ Styles]
Format: Name, Fontname
Style: Style1,Arial
Style: Style2,Arial
Style: Style3,Noto Sans
"""
    queries = extract_fonts(content, Path("ep1.mkv"), "Test")
    assert len(queries) == 2
    names = sorted([q.requested_name for q in queries])
    assert names == ["Arial", "Noto Sans"]

def test_extract_fonts_empty():
    content = """[Script Info]
Title: Empty
"""
    queries = extract_fonts(content, Path("ep1.mkv"), "Test")
    assert queries == []

def test_repair_ass_valid():
    path = FIXTURE_DIR / "valid_3_style.ass"
    repaired = repair_ass(path)
    assert "[V4+ Styles]" in repaired
    assert "Style: Default,Arial" in repaired

def test_repair_ass_missing_styles_raises_error():
    path = FIXTURE_DIR / "corrupt_missing_section.ass"
    with pytest.raises(EncodingRepairError):
        repair_ass(path)

def test_repair_ass_malformed_style_line_skipped():
    path = FIXTURE_DIR / "malformed_style_line.ass"
    repaired = repair_ass(path)
    
    assert "Style: Default,Arial" in repaired
    assert "Style: Normal,Times New Roman" in repaired
    # Malformed style line should be skipped (not present in output)
    assert "Style: Malformed" not in repaired
    assert "OnlySomeFieldsHere" not in repaired
