# Quickstart: Font System

**Feature**: 003-font-system | **Date**: 2026-05-26

## Usage Examples

### 1. Create and Query Font Cache

```python
from pathlib import Path
from src.core.font_cache import FontCache

cache = FontCache(cache_dir=Path("D:/Entertainment/.anime_studio/font_cache"))

# Lookup
asset = cache.lookup("Roboto")
if asset:
    print(f"Cache hit: {asset.file_path}, layer={asset.layer_found}")
else:
    print("Cache miss — proceed to hunters")

# Write-back after hunter success
from src.models.font import FontPayload
payload = FontPayload(
    font_name="Roboto Regular",
    font_data=b"...",
    file_extension=".ttf",
    source="google_fonts",
    nameids={1: "Roboto", 2: "Regular", 4: "Roboto Regular"},
)
asset = cache.store(payload, layer_found=5)
```

### 2. Register Hunters and Resolve Fonts

```python
from src.hunters.registry import HunterRegistry
from src.core.font_resolver import FontResolver
from src.models.font import FontQuery
from pathlib import Path

registry = HunterRegistry()
registry.register(my_cache_hunter)
registry.register(my_network_hunter)

resolver = FontResolver(registry=registry, cache=cache, config=app_config)

query = FontQuery(
    requested_name="Roboto",
    anime_title="Frieren",
    episode_path=Path("D:/Anime/Frieren/S01E01.mkv"),
)

result = await resolver.resolve(query)
# result is FontAsset on success, raises FontMatchError on full exhaustion
```

### 3. Circuit Breaker Usage

```python
from src.core.circuit_breaker import CircuitBreaker

cb = CircuitBreaker(
    hunter_name="google_fonts",
    threshold=3,
    cooldown_s=60.0,
)

if cb.can_execute():
    try:
        result = await hunter.search(query)
        cb.record_success()
    except HunterError:
        cb.record_failure()
else:
    print(f"Circuit OPEN for {cb._hunter_name}, skipping")
```

### 4. Startup Ping

```python
from src.core.font_resolver import FontResolver

resolver = FontResolver(registry=registry, cache=cache, config=app_config)
await resolver.startup_ping()
# All unreachable network hunters now have OPEN circuits
# Pipeline proceeds with local-only resolution as fallback
```

### 5. Subtitle Font Extraction

```python
from pathlib import Path
from src.core.subtitle_repair import extract_fonts, repair_ass

ass_path = Path("D:/Anime/Frieren/S01E01.ass")

# Repair first (idempotent)
repaired_content = repair_ass(ass_path)

# Extract font queries
queries = extract_fonts(repaired_content, episode_path=ass_path.with_suffix(".mkv"), anime_title="Frieren")
for q in queries:
    print(f"Need font: {q.requested_name}")
```

## Test Scenarios

### CircuitBreaker State Transitions

```
CLOSED --[3 failures]--> OPEN --[60s cooldown]--> HALF_OPEN --[success]--> CLOSED
                                                          --[failure]--> OPEN
```

### Font Resolution Order

```
Query "Roboto" →
  Layer 1 (Cache): MISS
  Layer 2 (MKV): MISS
  Layer 3 (Sibling): MISS
  Layer 4 (System): MISS
  Layer 5 (Google Fonts): HIT → FontPayload → Cache write-back → FontAsset
```
