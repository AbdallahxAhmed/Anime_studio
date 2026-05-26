from pydantic import BaseModel, ConfigDict, Field

from src.models._types import SerializablePath


class FontQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    requested_name: str = Field(min_length=1)
    anime_title: str = Field(min_length=1)
    episode_path: SerializablePath


class FontAsset(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    file_path: SerializablePath
    source: str
    layer_found: int = Field(ge=0, le=6)
    cache_hit: bool
    nameids: dict[int, str]
    is_patched: bool = False
    patch_reason: str | None = None


class HunterResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: FontQuery
    font_asset: FontAsset | None = None
    success: bool
    hunter_name: str
    duration_ms: float = Field(ge=0)
    attempts: int = Field(ge=1)


class FontPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    font_name: str = Field(min_length=1)
    font_data: bytes
    file_extension: str = Field(min_length=1)
    source: str = Field(min_length=1)
    nameids: dict[int, str]
    metadata: dict[str, str]
