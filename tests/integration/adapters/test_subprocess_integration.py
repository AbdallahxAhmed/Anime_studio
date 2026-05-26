import sys
import pytest
from src.adapters.subprocess import SubprocessAdapter


@pytest.mark.integration
@pytest.mark.anyio
async def test_subprocess_integration_success():
    adapter = SubprocessAdapter()
    
    # Run python to print hello
    args = [sys.executable, "-c", "print('hello from integration test')"]
    result = await adapter.execute(args, timeout=10.0)
    
    assert result.success is True
    assert result.exit_code == 0
    assert "hello from integration test" in result.stdout.strip()
    assert result.duration_ms > 0
    assert result.suggestion is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_subprocess_integration_failure():
    adapter = SubprocessAdapter()
    
    # Run python that exits with code 5
    args = [sys.executable, "-c", "import sys; sys.exit(5)"]
    result = await adapter.execute(args, timeout=10.0)
    
    assert result.success is False
    assert result.exit_code == 5
    assert result.duration_ms > 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_subprocess_integration_timeout():
    adapter = SubprocessAdapter()
    
    # Run python that sleeps for a long time
    args = [sys.executable, "-c", "import time; time.sleep(10.0)"]
    # Enforce a 0.2 second timeout
    result = await adapter.execute(args, timeout=0.2)
    
    assert result.success is False
    assert result.exit_code == -2
    assert "timed out" in result.suggestion
