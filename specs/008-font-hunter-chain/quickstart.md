# Quickstart: Phase 6.6 — Font Hunter Chain Implementation

## For Gemini (Implementation Agent)

### Prerequisites
- Read [plan.md](specs/008-font-hunter-chain/plan.md) fully
- Read [constitution.md](.specify/memory/constitution.md) §V (Plugin Registry), §III (Async-First), §I (Hexagonal)
- Understand [HunterProtocol](src/ports/font_hunter.py) interface
- Understand [HunterRegistry](src/hunters/registry.py) registration pattern
- Understand [SystemFontHunter](src/hunters/system_font_hunter.py) as reference implementation

### Implementation Order (by dependency)

**Task Group 1 — Foundation** (no dependencies):
1. Create `src/hunters/sources/__init__.py`
2. Create `src/hunters/sources/_hunter_utils.py` (shared utilities)
3. Fix `SystemFontHunter.priority` from 4 → 3

**Task Group 2 — Local Hunters** (depends on Group 1):
4. `SiblingFontHunter` — filesystem only, simplest
5. `MkvExtractHunter` — needs SubprocessPort

**Task Group 3 — Network Hunters** (depends on Group 1):
6. `GoogleFontsHunter` — primary, best-documented API
7. `FontSquirrelHunter`
8. `DaFontHunter`
9. `FontSpaceHunter`
10. `BeFontsHunter`
11. `ArabicFontsHunter`

**Task Group 4 — Nuclear Option** (depends on Groups 1-3):
12. `SearchEngineHunter` — DuckDuckGo HTML scraping

**Task Group 5 — Integration** (depends on ALL above):
13. Register ALL hunters in `bootstrap.py`
14. Update `font_resolver.py` error message
15. Update `COMPACT_STATE.md` — remove FuzzyMatch

**Task Group 6 — Tests** (parallel with each task):
16. Unit tests for each hunter

### Key Patterns (copy from SystemFontHunter)

Every hunter class MUST have:
```python
class XxxHunter:
    name: str = "XxxHunter"
    priority: int = N
    rate_limit: float = X.X
    circuit_breaker_threshold: int = 3
    ping_url: str | None = "https://..."

    def supports(self, query: FontQuery) -> bool: ...
    async def search(self, query: FontQuery) -> list[HunterResult]: ...
    async def download(self, result: HunterResult) -> FontPayload: ...
```

### Critical Rules
- **httpx async only** — never `requests` or `urllib`
- **Proxy from config** — `httpx.AsyncClient(proxy=self._proxy)`
- **fontTools verify after EVERY download** — call `verify_font()` from `_hunter_utils`
- **asyncio.sleep()** — never `time.sleep()` for rate limiting
- **is_cacheable=True** for all downloaded fonts (except system fonts)
- **No fuzzy matching** — exact name match only
