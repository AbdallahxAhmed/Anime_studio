import pytest
from src.hunters.registry import HunterRegistry
from src.ports.font_hunter import HunterProtocol
from src.core.circuit_breaker import CircuitBreakerState
from src.models.font import FontQuery, FontPayload, HunterResult

class ConformingMockHunter:
    def __init__(self, name: str, priority: int = 1, cb_threshold: int = 3):
        self.name = name
        self.priority = priority
        self.rate_limit = 1.0
        self.circuit_breaker_threshold = cb_threshold
        self.ping_url = None

    def supports(self, query: FontQuery) -> bool:
        return True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        return FontPayload(
            font_name="Dummy",
            font_data=b"",
            file_extension="ttf",
            source=self.name,
            nameids={},
            metadata={}
        )

class NonConformingMockHunter:
    def __init__(self):
        # Missing supports, search, download methods
        self.name = "NonConforming"

def test_hunter_registry_register_valid():
    registry = HunterRegistry()
    hunter = ConformingMockHunter("HunterA")
    registry.register(hunter)
    assert len(list(registry.iter_hunters())) == 1

def test_hunter_registry_reject_invalid():
    registry = HunterRegistry()
    with pytest.raises(TypeError):
        registry.register(NonConformingMockHunter()) # type: ignore

def test_hunter_registry_reject_duplicate_names():
    registry = HunterRegistry()
    registry.register(ConformingMockHunter("HunterA"))
    with pytest.raises(ValueError):
        registry.register(ConformingMockHunter("HunterA"))

def test_hunter_registry_priority_ordering():
    registry = HunterRegistry()
    h1 = ConformingMockHunter("Hunter1", priority=10)
    h2 = ConformingMockHunter("Hunter2", priority=1)
    h3 = ConformingMockHunter("Hunter3", priority=5)
    
    registry.register(h1)
    registry.register(h2)
    registry.register(h3)
    
    hunters = list(registry.iter_hunters())
    assert [h.name for h in hunters] == ["Hunter2", "Hunter3", "Hunter1"]

def test_hunter_registry_circuit_breakers():
    registry = HunterRegistry()
    h = ConformingMockHunter("HunterA", cb_threshold=2)
    registry.register(h)
    
    cb = registry.get_circuit("HunterA")
    assert cb.state == CircuitBreakerState.CLOSED
    
    # Trigger circuit breaker trip
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    
    # Iteration skips circuit-broken hunters
    hunters = list(registry.iter_hunters())
    assert len(hunters) == 0
