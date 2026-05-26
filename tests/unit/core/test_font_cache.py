import pytest
from src.core.font_cache import FontCache
from src.models.font import FontPayload, FontAsset

# Note: These tests are written test-first and will fail until FontCache is implemented.


@pytest.fixture
def temp_cache_dir(tmp_path):
    return tmp_path / "font_cache"


def test_font_cache_lookup_miss(temp_cache_dir):
    cache = FontCache(temp_cache_dir)
    asset = cache.lookup("NonExistentFont")
    assert asset is None


def test_font_cache_store_and_lookup_hit(temp_cache_dir):
    cache = FontCache(temp_cache_dir)
    payload = FontPayload(
        font_name="Roboto-Regular",
        font_data=b"dummy_font_bytes",
        file_extension="ttf",
        source="google_fonts",
        nameids={1: "Roboto", 2: "Regular"},
        metadata={"license": "Apache 2.0"},
    )

    asset = cache.store(payload, layer_found=5)
    assert isinstance(asset, FontAsset)
    assert asset.name == "Roboto-Regular"
    assert asset.source == "google_fonts"
    assert asset.layer_found == 5
    assert asset.cache_hit is False
    assert asset.file_path.exists()
    assert asset.file_path.read_bytes() == b"dummy_font_bytes"

    # Now lookup should result in a hit
    asset_hit = cache.lookup("Roboto-Regular")
    assert asset_hit is not None
    assert asset_hit.name == "Roboto-Regular"
    assert asset_hit.cache_hit is True
    assert asset_hit.file_path == asset.file_path


def test_font_cache_version_validation(temp_cache_dir):
    # Setup index with matching cache_version
    temp_cache_dir.mkdir(parents=True, exist_ok=True)
    toml_path = temp_cache_dir / "font_library.toml"
    toml_path.write_text(
        'cache_version = "3.0"\n\n[fonts."Arial"]\nfile = "Arial.ttf"\nsource = "system"\nlayer_found = 4\nadded = "2026-05-26T10:30:00"\nnameids = {1 = "Arial"}\n',
        encoding="utf-8",
    )
    # Write Arial.ttf dummy file
    (temp_cache_dir / "Arial.ttf").write_bytes(b"arial_bytes")

    cache = FontCache(temp_cache_dir)
    # matching version loads normally
    asset = cache.lookup("Arial")
    assert asset is not None
    assert asset.name == "Arial"

    # Now write stale version
    toml_path.write_text(
        'cache_version = "2.0"\n\n[fonts."Arial"]\nfile = "Arial.ttf"\nsource = "system"\nlayer_found = 4\nadded = "2026-05-26T10:30:00"\nnameids = {1 = "Arial"}\n',
        encoding="utf-8",
    )
    cache_stale = FontCache(temp_cache_dir)
    # stale version triggers rebuild (which deletes Arial entry or rebuilds it from directory scan)
    # Arial.ttf is scanned and registered with source="unknown" or similar scan behavior
    asset_rebuilt = cache_stale.lookup("Arial")
    assert asset_rebuilt is not None
    assert asset_rebuilt.name == "Arial"
    assert asset_rebuilt.source == "scanned"  # or what we define as scanned source


def test_font_cache_corrupted_toml_triggers_rescan(temp_cache_dir):
    temp_cache_dir.mkdir(parents=True, exist_ok=True)
    toml_path = temp_cache_dir / "font_library.toml"
    toml_path.write_text("invalid [[ toml format line }", encoding="utf-8")

    # Write some font files to scan
    (temp_cache_dir / "ScannedFont.ttf").write_bytes(b"scanned_font_bytes")

    cache = FontCache(temp_cache_dir)
    # Rebuild from scan should detect ScannedFont.ttf (normalized from file name or parsed)
    # and load it properly
    asset = cache.lookup("ScannedFont")
    assert asset is not None
    assert asset.name == "ScannedFont"
    assert asset.source == "scanned"
