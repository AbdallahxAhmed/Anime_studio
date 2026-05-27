# Quickstart: Hotfix — Core Stability & Hunter Resolution (v1.7.0)

## What Changed

This hotfix resolves three critical pipeline failures:

### 1. Scanner No Longer Processes Trash Directories
The library scanner now excludes all dot-prefixed directories (`.anime_studio_trash`, `.git`, etc.) from its recursive scan. MKV files previously moved to trash are no longer rediscovered as valid episodes.

### 2. Tool Discovery Now Logs Every Step
When `alass` or another tool isn't found, the DEBUG log now shows every path that was checked. This makes it trivial to diagnose "tool not found" issues:

```
DEBUG: Discovery step 1: checking scoop shim | tool=alass | path=C:\Users\you\scoop\shims\alass.exe | exists=False
DEBUG: Discovery step 2: checking scoop app dir | tool=alass | path=C:\Users\you\scoop\apps\alass\current | exists=False
DEBUG: Discovery step 3: checking mpv directory | tool=alass | path=C:\Program Files\mpv\alass.exe | exists=False
DEBUG: Discovery step 4: checking Program Files | tool=alass | path=C:\Program Files\alass | exists=False
DEBUG: Discovery step 5: checking shutil.which | tool=alass | result=None
WARNING: optional dependency missing | name=alass
```

### 3. Font Resolution Actually Works Now

**System fonts**: The `SystemFontHunter` now:
- Scans `.ttc` files (TrueType Collections), not just `.ttf`/`.otf`
- Applies progressive normalization when exact match fails (strips "Regular"/"Normal" suffixes, expands weight synonyms like "Semibold" ↔ "Demi Bold")

**Network fonts**: A new `NetworkFontHunter` (Google Fonts API) provides network-based resolution for fonts not found locally. Requires adding `google_fonts_api_key` to your `config.toml`.

**Proxy support**: `startup_ping()` now correctly uses the `proxy` setting from `config.toml`. Users behind SOCKS/HTTP proxies no longer get all network hunters disabled at startup.

**Softer circuit breaker**: A failed startup ping now records 1 failure (not 3), giving the hunter a fair chance during actual resolution instead of being immediately disabled.

## Configuration

### New config.toml field

```toml
# Optional: enables Google Fonts API-based font resolution
google_fonts_api_key = "your-api-key-here"
```

When absent, the network font hunter silently deactivates — no errors, no crashes.

### Existing proxy field (now actually works)

```toml
# Optional: proxy for all network requests including startup pings
proxy = "socks5://127.0.0.1:1080"
```

## Verification

```bash
# Run the full test suite
pytest tests/ -v

# Run only the hotfix-related tests
pytest tests/unit/core/test_library_scanner.py -v
pytest tests/unit/adapters/test_dependency_checker.py -v
pytest tests/unit/hunters/ -v
pytest tests/unit/core/test_font_resolver.py -v
```
