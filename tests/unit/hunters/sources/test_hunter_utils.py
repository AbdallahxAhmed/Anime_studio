import io
import zipfile
from src.hunters.sources._hunter_utils import (
    verify_font,
    extract_fonts_from_zip,
    normalize_font_name,
    font_name_matches,
)


def test_verify_font_valid() -> None:
    with open("tests/fixtures/fonts/valid.ttf", "rb") as f:
        data = f.read()
    nameids = verify_font(data, "valid.ttf")
    assert nameids is not None
    assert nameids[1] == "TestTTF"
    assert nameids[4] == "TestTTF Regular"
    assert nameids[6] == "TestTTF-Regular"


def test_verify_font_invalid() -> None:
    with open("tests/fixtures/fonts/corrupt.ttf", "rb") as f:
        data = f.read()
    nameids = verify_font(data, "corrupt.ttf")
    assert nameids is None


def test_extract_fonts_from_zip() -> None:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        with open("tests/fixtures/fonts/valid.ttf", "rb") as f:
            zf.writestr("valid.ttf", f.read())
        with open("tests/fixtures/fonts/corrupt.ttf", "rb") as f:
            zf.writestr("subdir/corrupt.ttf", f.read())
        zf.writestr("readme.txt", b"not a font file")

    zip_data = zip_buffer.getvalue()
    results = extract_fonts_from_zip(zip_data)

    assert len(results) == 1
    filename, font_bytes, nameids = results[0]
    assert filename == "valid.ttf"
    assert nameids[1] == "TestTTF"


def test_normalize_font_name() -> None:
    assert normalize_font_name("Open-Sans_Bold") == "open sans bold"
    assert normalize_font_name(" Roboto ") == "roboto"


def test_font_name_matches() -> None:
    nameids = {1: "Test Font", 4: "Test Font Bold", 6: "TestFont-Bold"}
    assert font_name_matches("Test Font", nameids) is True
    assert font_name_matches("test-font", nameids) is True
    assert font_name_matches("Test Font Bold", nameids) is True
    assert font_name_matches("testfont-bold", nameids) is True
    assert font_name_matches("Other Font", nameids) is False
