from src.errors import (
    AnimeStudioError,
    FontMatchError,
    HunterError,
    EncodingRepairError,
)


def test_font_match_error_inheritance():
    err = FontMatchError("Font resolution failed")
    assert isinstance(err, AnimeStudioError)
    assert str(err) == "Font resolution failed"


def test_hunter_error_inheritance():
    err = HunterError("Hunter source failed")
    assert isinstance(err, AnimeStudioError)
    assert str(err) == "Hunter source failed"


def test_encoding_repair_error_inheritance():
    err = EncodingRepairError("Encoding repair failed")
    assert isinstance(err, AnimeStudioError)
    assert str(err) == "Encoding repair failed"
