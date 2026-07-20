# Data Model: Phase 6.6 — Font Hunter Chain

## Existing Entities (NO CHANGES)

### FontQuery (frozen)
- `requested_name: str` — font name from ASS
- `anime_title: str` — for context
- `episode_path: SerializablePath` — source episode

### FontAsset (frozen)
- `name: str`, `file_path: Path`, `source: str`
- `layer_found: int` (0–6), `cache_hit: bool`
- `nameids: dict[int, str]`, `is_cacheable: bool`

### HunterResult (frozen)
- `query: FontQuery`, `font_asset: FontAsset | None`
- `success: bool`, `hunter_name: str`
- `duration_ms: float`, `attempts: int`

### FontPayload (frozen)
- `font_name: str`, `font_data: bytes`
- `file_extension: str`, `source: str`
- `nameids: dict[int, str]`, `metadata: dict[str, str]`

### HunterProtocol (Protocol)
- `name: str`, `priority: int`, `rate_limit: float`
- `circuit_breaker_threshold: int`, `ping_url: str | None`
- `supports(query) -> bool`
- `search(query) -> list[HunterResult]`
- `download(result) -> FontPayload`

## New Hunter Classes

All new hunters implement `HunterProtocol`. No new models needed — all use existing `FontQuery`, `HunterResult`, `FontPayload`, `FontAsset`.

### MkvExtractHunter (Layer 1)
- Scans library MKVs for embedded font attachments
- Uses `SubprocessPort` for `mkvmerge -J` and `mkvextract attachments`
- Returns `FontPayload` with `is_cacheable=True`

### SiblingFontHunter (Layer 2)
- Scans `Fonts/` and `fonts/` dirs adjacent to episode path
- Pure filesystem, no network
- Returns `FontAsset` with `is_cacheable=True` (copy to cache)

### GoogleFontsHunter (Layer 4)
### FontSquirrelHunter (Layer 4)
### DaFontHunter (Layer 4)
### FontSpaceHunter (Layer 4)
### BeFontsHunter (Layer 4)
### ArabicFontsHunter (Layer 4)
- All download from their respective repository
- Return `FontPayload` with font bytes
- `is_cacheable=True` — stored in font_cache/

### SearchEngineHunter (Layer 5)
- DuckDuckGo HTML search
- Parses results, downloads from found URLs
- `is_cacheable=True`

## State Transitions

None — all hunters are stateless. Circuit breaker state lives in `HunterRegistry._circuits`.
