from typing import Iterator
import structlog
from src.ports.font_hunter import HunterProtocol
from src.core.circuit_breaker import CircuitBreaker

logger = structlog.get_logger()


class HunterRegistry:
    """Registry orchestrating priority-ordered hunter iteration with circuit breaker awareness."""

    def __init__(self, cooldown_s: float = 60.0):
        self.cooldown_s = cooldown_s
        self._hunters: dict[str, HunterProtocol] = {}
        self._circuits: dict[str, CircuitBreaker] = {}

    def register(self, hunter: HunterProtocol) -> None:
        """Register a valid hunter protocol conforming object. Rejects duplicates."""
        if not isinstance(hunter, HunterProtocol):
            logger.error(
                "Registry rejected non-conforming hunter object", hunter=hunter
            )
            raise TypeError("Object does not conform to HunterProtocol")

        if hunter.name in self._hunters:
            logger.error("Registry rejected duplicate hunter name", name=hunter.name)
            raise ValueError(f"Hunter with name {hunter.name} is already registered")

        self._hunters[hunter.name] = hunter
        self._circuits[hunter.name] = CircuitBreaker(
            hunter_name=hunter.name,
            threshold=hunter.circuit_breaker_threshold,
            cooldown_s=self.cooldown_s,
        )
        logger.info("Hunter registered", name=hunter.name, priority=hunter.priority)

    def get_circuit(self, hunter_name: str) -> CircuitBreaker:
        """Get the circuit breaker instance for a given hunter."""
        if hunter_name not in self._circuits:
            # If requested for a name we don't have registered yet, fallback create
            self._circuits[hunter_name] = CircuitBreaker(
                hunter_name=hunter_name,
                threshold=3,
                cooldown_s=self.cooldown_s,
            )
        return self._circuits[hunter_name]

    def iter_hunters(self) -> Iterator[HunterProtocol]:
        """Iterate hunters in ascending priority order, skipping OPEN circuit ones."""
        sorted_hunters = sorted(self._hunters.values(), key=lambda h: h.priority)
        for hunter in sorted_hunters:
            cb = self._circuits[hunter.name]
            if not cb.can_execute():
                logger.warning(
                    "Skipping circuit-broken hunter",
                    hunter_name=hunter.name,
                    state=cb.state,
                )
                continue
            yield hunter
