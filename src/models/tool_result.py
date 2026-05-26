from pydantic import BaseModel, ConfigDict, Field


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = Field(ge=0)
    suggestion: str | None = None
