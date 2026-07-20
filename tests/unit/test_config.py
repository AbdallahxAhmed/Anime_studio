import pytest
from pathlib import Path
from pydantic import ValidationError

from src.config import AppConfig


def test_app_config_defaults():
    config = AppConfig()
    assert config.circuit_breaker_cooldown_s == 60.0
    assert config.font_cache_path is None
    assert config.startup_ping_timeout_s == 2.0
    # Also verify existing defaults just to be sure
    assert config.max_concurrent_disk_io == 4
    assert config.default_timeout_s == 120


def test_app_config_validation():
    # circuit_breaker_cooldown_s must be float-like and ge 0
    with pytest.raises(ValidationError):
        AppConfig(circuit_breaker_cooldown_s="not a float")

    with pytest.raises(ValidationError):
        AppConfig(circuit_breaker_cooldown_s=-1.0)

    # startup_ping_timeout_s must be float-like and ge 0
    with pytest.raises(ValidationError):
        AppConfig(startup_ping_timeout_s="not a float")

    with pytest.raises(ValidationError):
        AppConfig(startup_ping_timeout_s=-0.5)

    # font_cache_path can be Path or None, and string is coerced to Path
    config = AppConfig(font_cache_path="D:\\some\\path")
    assert isinstance(config.font_cache_path, Path)
    assert config.font_cache_path == Path("D:\\some\\path")


def test_app_config_load_from_toml(tmp_path):
    toml_content = """
    [app]
    proxy = "http://localhost:8080"
    max_concurrent_disk_io = 8
    circuit_breaker_cooldown_s = 30.5
    font_cache_path = 'D:\\custom\\cache'
    startup_ping_timeout_s = 5.0
    """
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(toml_content, encoding="utf-8")

    config = AppConfig.load_from_toml(toml_file)
    assert config.proxy == "http://localhost:8080"
    assert config.max_concurrent_disk_io == 8
    assert config.circuit_breaker_cooldown_s == 30.5
    assert config.font_cache_path == Path("D:\\custom\\cache")
    assert config.startup_ping_timeout_s == 5.0


def test_app_config_load_from_toml_missing_file():
    # If file doesn't exist, should return default config
    config = AppConfig.load_from_toml(Path("non_existent_file.toml"))
    assert config.circuit_breaker_cooldown_s == 60.0
    assert config.font_cache_path is None
    assert config.library_path is None


def test_app_config_save_to_toml(tmp_path):
    toml_file = tmp_path / "config.toml"
    config = AppConfig(
        proxy="socks5://localhost:1080",
        max_concurrent_disk_io=5,
        library_path=Path("D:\\Anime"),
    )
    config.save_to_toml(toml_file)

    # Reload from TOML and check values
    reloaded = AppConfig.load_from_toml(toml_file)
    assert reloaded.proxy == "socks5://localhost:1080"
    assert reloaded.max_concurrent_disk_io == 5
    assert reloaded.library_path == Path("D:\\Anime")
