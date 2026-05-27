# Contract: MkvextractPort

## Interface

```python
@runtime_checkable
class MkvextractPort(Protocol):
    async def extract_track(
        self,
        mkv_path: Path,
        track_id: int,
        output_path: Path,
        timeout: float = 120.0,
    ) -> ToolResult: ...
```

## Preconditions

- `mkv_path` must be an existing MKV file
- `track_id` must be a valid 0-based track ID from `mkvmerge -J` output
- `output_path` parent directory must exist
- Caller must have acquired the disk I/O semaphore before calling

## Postconditions

### Success (`ToolResult.success == True`, exit_code 0 or 1)
- File at `output_path` contains the extracted track content
- For ASS/SSA tracks, the file is a valid standalone `.ass` file
- `ToolResult.duration_ms` reflects actual extraction time

### Failure (`ToolResult.success == False`)
- `output_path` may or may not exist (partial write possible)
- `ToolResult.stderr` contains mkvextract error message
- `ToolResult.exit_code` is `2` (mkvextract error) or negative (timeout/crash)
- No exception is raised — failure is communicated through `ToolResult`

## Exit Code Semantics

| Code | Meaning |
|------|---------|
| `0` | Success, no warnings |
| `1` | Success with warnings |
| `2` | Error |
| `-2` | Timeout (killed by SubprocessAdapter) |
| `-3` | Binary not found |
| `-4` | Execution exception |
