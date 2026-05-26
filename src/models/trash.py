from datetime import datetime
from pydantic import BaseModel, ConfigDict
from src.models._types import SerializablePath


class TrashReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    original_path: SerializablePath
    trash_path: SerializablePath
    deletion_time: datetime
    expiration_time: datetime
