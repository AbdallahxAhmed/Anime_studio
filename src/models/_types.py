from pathlib import Path
from typing import Annotated

from pydantic import PlainSerializer

# Annotated Path that serializes as a POSIX string
SerializablePath = Annotated[
    Path, PlainSerializer(lambda p: p.as_posix(), return_type=str)
]
