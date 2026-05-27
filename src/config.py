import os
import sys
import tomllib
from pathlib import Path
from pydantic import BaseModel, Field

CACHE_VERSION = "3.0"


class SubtitleConfig(BaseModel):
    preferred_language: str = "ara"
    strict_language: bool = True


class AppConfig(BaseModel):
    proxy: str | None = None
    max_concurrent_disk_io: int = Field(default=4, ge=1)
    default_timeout_s: int = Field(default=120, ge=1)
    mux_timeout_s: int = Field(default=300, ge=1)
    trash_max_age_days: int = Field(default=30, ge=1)
    circuit_breaker_cooldown_s: float = Field(default=60.0, ge=0.0)
    font_cache_path: Path | None = None
    startup_ping_timeout_s: float = Field(default=2.0, ge=0.0)
    library_path: Path | None = None
    subtitle: SubtitleConfig = SubtitleConfig()

    def save_to_toml(self, file_path: Path | str | None = None) -> None:
        """Save config parameters to TOML file."""
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
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["[app]"]
        # Use model_dump() for pydantic v2 compatible dict dump
        data = self.model_dump()
        app_data = {k: v for k, v in data.items() if k != "subtitle"}
        for key, value in app_data.items():
            if value is None:
                continue
            if isinstance(value, Path):
                val_str = str(value).replace("\\", "/")
                lines.append(f'{key} = "{val_str}"')
            elif isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, bool):
                lines.append(f'{key} = {str(value).lower()}')
            else:
                lines.append(f'{key} = {value}')

        lines.append("")
        lines.append("[subtitle]")
        for key, value in self.subtitle.model_dump().items():
            if isinstance(value, bool):
                lines.append(f'{key} = {str(value).lower()}')
            elif isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            else:
                lines.append(f'{key} = {value}')

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

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
            if isinstance(data.get("app"), dict):
                config_data = dict(data["app"])
                if isinstance(data.get("subtitle"), dict):
                    config_data["subtitle"] = data["subtitle"]
            else:
                config_data = data
            return cls(**config_data)
        except Exception as e:
            from src.errors import ConfigurationError

            raise ConfigurationError(
                f"Failed to parse config file at {path}: {e}"
            ) from e
