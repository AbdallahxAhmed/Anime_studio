# Quickstart: Pipeline Orchestration

**Feature**: 004-pipeline | **Date**: 2026-05-26

## Verify Setup

```bash
# Ensure external tools are available
python -c "from src.adapters import DependencyChecker; DependencyChecker().discover_all()"

# Run existing tests to confirm baseline
pytest tests/unit/ -v
```

## Run Pipeline (after implementation)

```python
import asyncio
from pathlib import Path
from src.config import AppConfig
from src.core.pipeline_runner import PipelineRunner
from src.core.font_resolver import FontResolver
from src.core.font_cache import FontCache
from src.hunters.registry import HunterRegistry
from src.adapters import SubprocessAdapter, DependencyChecker
from src.adapters.filesystem import FilesystemAdapter
from src.models.pipeline import PipelineConfig

async def main():
    config = AppConfig.load_from_toml()
    
    # Setup dependencies
    dep_checker = DependencyChecker()
    tool_registry = dep_checker.discover_all()
    
    cache = FontCache(config.font_cache_path or Path("D:/Entertainment/.anime_studio/font_cache"))
    hunter_registry = HunterRegistry(cooldown_s=config.circuit_breaker_cooldown_s)
    font_resolver = FontResolver(hunter_registry, cache, config)
    
    subprocess_adapter = SubprocessAdapter()
    filesystem = FilesystemAdapter()
    
    # Create pipeline runner
    runner = PipelineRunner(
        font_resolver=font_resolver,
        subprocess_adapter=subprocess_adapter,
        filesystem=filesystem,
        tool_registry=tool_registry,
        config=config,
    )
    
    # Configure and run
    pipeline_config = PipelineConfig(
        library_path=Path("D:/Entertainment/Anime/SomeAnime"),
        dry_run=False,
        sync_enabled=False,
    )
    
    report = await runner.run(pipeline_config)
    print(f"Pipeline complete: {len(report.episodes)} episodes processed")

asyncio.run(main())
```

## Test Scenarios

### Unit Test: Library Scanner
```python
# Test MKV/ASS pairing by stem matching
# Test empty directory → empty list
# Test MKV without matching ASS → not included
# Test case-insensitive matching
```

### Unit Test: Pipeline Runner
```python
# Test full pipeline with mocked adapters
# Test individual episode failure doesn't abort pipeline
# Test dry-run mode skips mutations
# Test report generation after run
```

### Integration Test
```python
# @pytest.mark.integration
# Test with real mkvmerge binary
# Test with sample MKV + ASS files
# Verify output MKV has correct tracks
```
