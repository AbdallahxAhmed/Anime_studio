import pytest
from pathlib import Path
from pydantic import ValidationError

from src.models.font import FontQuery, FontAsset, HunterResult, FontPayload


def test_font_query_valid():
    query = FontQuery(
        requested_name="Arial",
        anime_title="Naruto",
        episode_path=Path("/videos/naruto_ep1.mkv"),
    )
    assert query.requested_name == "Arial"
    assert query.anime_title == "Naruto"
    assert query.episode_path == Path("/videos/naruto_ep1.mkv")

    # Test JSON round-trip
    dumped = query.model_dump(mode="json")
    assert dumped["episode_path"] == "/videos/naruto_ep1.mkv"
    assert isinstance(dumped["episode_path"], str)


def test_font_query_validation():
    with pytest.raises(ValidationError):
        FontQuery(requested_name="", anime_title="Naruto", episode_path=Path("path"))
    with pytest.raises(ValidationError):
        FontQuery(requested_name="Arial", anime_title="", episode_path=Path("path"))


def test_font_asset_valid():
    asset = FontAsset(
        name="Arial",
        file_path=Path("/fonts/arial.ttf"),
        source="system",
        layer_found=1,
        cache_hit=False,
        nameids={1: "Arial", 2: "Regular"},
    )
    assert asset.name == "Arial"
    assert asset.is_patched is False
    assert asset.patch_reason is None
    assert asset.is_cacheable is True

    # Test explicit is_cacheable=False
    uncacheable_asset = FontAsset(
        name="Arial",
        file_path=Path("/fonts/arial.ttf"),
        source="system",
        layer_found=1,
        cache_hit=False,
        nameids={1: "Arial", 2: "Regular"},
        is_cacheable=False,
    )
    assert uncacheable_asset.is_cacheable is False

    dumped = asset.model_dump(mode="json")
    assert dumped["file_path"] == "/fonts/arial.ttf"
    assert dumped["nameids"] == {"1": "Arial", "2": "Regular"}  # JSON stringifies keys
    assert dumped["is_cacheable"] is True


def test_font_asset_validation():
    with pytest.raises(ValidationError):
        FontAsset(
            name="",
            file_path=Path("f.ttf"),
            source="src",
            layer_found=1,
            cache_hit=False,
            nameids={},
        )
    with pytest.raises(ValidationError):
        FontAsset(
            name="A",
            file_path=Path("f.ttf"),
            source="src",
            layer_found=-1,
            cache_hit=False,
            nameids={},
        )
    with pytest.raises(ValidationError):
        FontAsset(
            name="A",
            file_path=Path("f.ttf"),
            source="src",
            layer_found=7,
            cache_hit=False,
            nameids={},
        )


def test_hunter_result_valid():
    query = FontQuery(
        requested_name="Arial", anime_title="Test", episode_path=Path("/test.mkv")
    )
    asset = FontAsset(
        name="Arial",
        file_path=Path("/fonts/arial.ttf"),
        source="test",
        layer_found=0,
        cache_hit=True,
        nameids={},
    )

    result = HunterResult(
        query=query,
        font_asset=asset,
        success=True,
        hunter_name="MockHunter",
        duration_ms=15.5,
        attempts=1,
    )
    assert result.success is True
    assert result.font_asset is not None

    dumped = result.model_dump(mode="json")
    assert dumped["query"]["episode_path"] == "/test.mkv"
    assert dumped["font_asset"]["file_path"] == "/fonts/arial.ttf"


def test_hunter_result_validation():
    query = FontQuery(
        requested_name="Arial", anime_title="Test", episode_path=Path("/test.mkv")
    )
    with pytest.raises(ValidationError):
        HunterResult(
            query=query,
            font_asset=None,
            success=False,
            hunter_name="H",
            duration_ms=-1.0,
            attempts=1,
        )
    with pytest.raises(ValidationError):
        HunterResult(
            query=query,
            font_asset=None,
            success=False,
            hunter_name="H",
            duration_ms=1.0,
            attempts=0,
        )


def test_frozen_immutability():
    query = FontQuery(requested_name="A", anime_title="B", episode_path=Path("C"))
    with pytest.raises(ValidationError):
        query.requested_name = "New"


class TestFontPayloadValidation:
    def test_font_payload_valid(self):
        payload = FontPayload(
            font_name="Arial",
            font_data=b"mock_bytes",
            file_extension="ttf",
            source="system",
            nameids={1: "Arial"},
            metadata={"version": "1.0"},
        )
        assert payload.font_name == "Arial"
        assert payload.font_data == b"mock_bytes"
        assert payload.file_extension == "ttf"
        assert payload.source == "system"
        assert payload.nameids == {1: "Arial"}
        assert payload.metadata == {"version": "1.0"}

    def test_font_payload_frozen(self):
        payload = FontPayload(
            font_name="Arial",
            font_data=b"mock_bytes",
            file_extension="ttf",
            source="system",
            nameids={},
            metadata={},
        )
        with pytest.raises(ValidationError):
            payload.font_name = "New Name"

    def test_font_payload_min_length(self):
        with pytest.raises(ValidationError):
            FontPayload(
                font_name="",
                font_data=b"mock_bytes",
                file_extension="ttf",
                source="system",
                nameids={},
                metadata={},
            )
        with pytest.raises(ValidationError):
            FontPayload(
                font_name="Arial",
                font_data=b"mock_bytes",
                file_extension="",
                source="system",
                nameids={},
                metadata={},
            )
        with pytest.raises(ValidationError):
            FontPayload(
                font_name="Arial",
                font_data=b"mock_bytes",
                file_extension="ttf",
                source="",
                nameids={},
                metadata={},
            )

    def test_font_payload_bytes_field(self):
        with pytest.raises(ValidationError):
            FontPayload(
                font_name="Arial",
                font_data=123,  # type: ignore
                file_extension="ttf",
                source="system",
                nameids={},
                metadata={},
            )
