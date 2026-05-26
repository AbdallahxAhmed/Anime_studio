from unittest.mock import patch
from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerState

# Note: These tests are written test-first and will fail until CircuitBreaker is implemented.


def test_circuit_breaker_initial_state():
    cb = CircuitBreaker(hunter_name="GoogleFonts", threshold=3, cooldown_s=10.0)
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.can_execute() is True


def test_circuit_breaker_trips_to_open():
    cb = CircuitBreaker(hunter_name="GoogleFonts", threshold=3, cooldown_s=10.0)

    cb.record_failure()
    assert cb.state == CircuitBreakerState.CLOSED

    cb.record_failure()
    assert cb.state == CircuitBreakerState.CLOSED

    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    assert cb.can_execute() is False


def test_circuit_breaker_cooldown_to_half_open():
    with patch("time.monotonic") as mock_time:
        start_time = 100.0
        mock_time.return_value = start_time

        cb = CircuitBreaker(hunter_name="GoogleFonts", threshold=2, cooldown_s=10.0)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.can_execute() is False

        # Advance time by less than cooldown
        mock_time.return_value = start_time + 5.0
        assert cb.can_execute() is False
        assert cb.state == CircuitBreakerState.OPEN

        # Advance time past cooldown
        mock_time.return_value = start_time + 11.0
        # can_execute() should transition to HALF_OPEN and return True
        assert cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN


def test_circuit_breaker_half_open_success_closes():
    with patch("time.monotonic") as mock_time:
        start_time = 100.0
        mock_time.return_value = start_time

        cb = CircuitBreaker(hunter_name="GoogleFonts", threshold=2, cooldown_s=10.0)
        cb.record_failure()
        cb.record_failure()

        # Advance time to half-open
        mock_time.return_value = start_time + 11.0
        assert cb.can_execute() is True

        # Success in HALF_OPEN should transition back to CLOSED
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.can_execute() is True


def test_circuit_breaker_half_open_failure_trips():
    with patch("time.monotonic") as mock_time:
        start_time = 100.0
        mock_time.return_value = start_time

        cb = CircuitBreaker(hunter_name="GoogleFonts", threshold=2, cooldown_s=10.0)
        cb.record_failure()
        cb.record_failure()

        # Advance time to half-open
        mock_time.return_value = start_time + 11.0
        assert cb.can_execute() is True

        # Failure in HALF_OPEN should transition back to OPEN
        mock_time.return_value = start_time + 12.0
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.can_execute() is False
