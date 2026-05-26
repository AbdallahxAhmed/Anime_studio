import os
import sys
import tomllib
from pathlib import Path
from pydantic import BaseModel, Field

CACHE_VERSION = "3.0"


class AppConfig(BaseModel):
    proxy: str | None = None
    max_concurrent_disk_io: int = Field(default=4, ge=1)
    default_timeout_s: int = Field(default=120, ge=1)
    mux_timeout_s: int = Field(default=300, ge=1)
    trash_max_age_days: int = Field(default=30, ge=1)
    circuit_breaker_cooldown_s: float = Field(default=60.0, ge=0.0)
    font_cache_path: Path | None = None
    startup_ping_timeout_s: float = Field(default=2.0, ge=0.0)

    @classmethod
    def load_from_toml(cls, file_path: Path | str | None = None) -> "AppConfig":
        if file_path is None:
            if sys.platform == "win32":
                app_data = os.environ.get("APPDATA")
                if app_data:
                    base_path = Path(app_data) / "AnimeStudio"
                else:
                    base_path = Path.home() / "AppData" / "Roaming" / "AnimeStudio"
            else:
                base_path = Path.home() / ".config" / "AnimeStudio"

            file_path = base_path / "config.toml"

        path = Path(file_path)
        if not path.is_file():
            return cls()

        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
            # Feed parsed dict directly into instantiation
            config_data = (
                data.get("app", data) if isinstance(data.get("app"), dict) else data
            )
            return cls(**config_data)
        except Exception as e:
            from src.errors import ConfigurationError

            raise ConfigurationError(
                f"Failed to parse config file at {path}: {e}"
            ) from e
