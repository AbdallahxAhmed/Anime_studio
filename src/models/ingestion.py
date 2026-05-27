from pydantic import BaseModel, ConfigDict, Field
from src.models._types import SerializablePath


class FontIngestionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    failed_details: list[tuple[SerializablePath, str]] = Field(default_factory=list)
    source: str = Field(min_length=1)
