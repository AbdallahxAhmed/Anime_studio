import time
from enum import StrEnum
import structlog

logger = structlog.get_logger()


class CircuitBreakerState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """In-memory state machine tracking failure counts for rate/circuit control."""

    __slots__ = (
        "_state",
        "_failure_count",
        "_threshold",
        "_cooldown_s",
        "_last_failure_time",
        "_hunter_name",
    )

    def __init__(self, hunter_name: str, threshold: int, cooldown_s: float):
        self._hunter_name = hunter_name
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    def can_execute(self) -> bool:
        """Check if execution is allowed based on current state and cooldown."""
        match self._state:
            case CircuitBreakerState.CLOSED | CircuitBreakerState.HALF_OPEN:
                return True
            case CircuitBreakerState.OPEN:
                now = time.monotonic()
                if (
                    self._last_failure_time is not None
                    and now - self._last_failure_time >= self._cooldown_s
                ):
                    logger.debug(
                        "Circuit breaker cooldown expired. Transitioning from OPEN to HALF_OPEN.",
                        hunter_name=self._hunter_name,
                    )
                    self._state = CircuitBreakerState.HALF_OPEN
                    return True
                logger.warning(
                    "Circuit breaker is OPEN. Skipping hunter execution.",
                    hunter_name=self._hunter_name,
                )
                return False

    def record_success(self) -> None:
        """Record a successful execution, resetting circuit breaker state."""
        match self._state:
            case CircuitBreakerState.HALF_OPEN:
                logger.info(
                    "Circuit breaker recovered. Transitioning from HALF_OPEN to CLOSED.",
                    hunter_name=self._hunter_name,
                )
                self._state = CircuitBreakerState.CLOSED
                self._failure_count = 0
                self._last_failure_time = None
            case _:
                self._failure_count = 0
                self._last_failure_time = None

    def record_failure(self) -> None:
        """Record a failure, potentially tripping circuit breaker state."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        match self._state:
            case CircuitBreakerState.CLOSED:
                if self._failure_count >= self._threshold:
                    logger.info(
                        "Circuit breaker tripped. Transitioning from CLOSED to OPEN.",
                        hunter_name=self._hunter_name,
                        failures=self._failure_count,
                        threshold=self._threshold,
                    )
                    self._state = CircuitBreakerState.OPEN
            case CircuitBreakerState.HALF_OPEN:
                logger.info(
                    "Circuit breaker failed in HALF_OPEN. Transitioning from HALF_OPEN to OPEN.",
                    hunter_name=self._hunter_name,
                )
                self._state = CircuitBreakerState.OPEN
                # Keep failure count at least at threshold
                self._failure_count = max(self._failure_count, self._threshold)
            case CircuitBreakerState.OPEN:
                pass
