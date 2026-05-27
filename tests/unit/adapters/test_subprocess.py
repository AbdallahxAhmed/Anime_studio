import ast
import asyncio
from pathlib import Path
import pytest
from src.adapters.subprocess import SubprocessAdapter


@pytest.mark.anyio
async def test_subprocess_success(mocker):
    adapter = SubprocessAdapter()

    mock_process = mocker.AsyncMock()
    mock_process.communicate.return_value = (b"hello stdout", b"hello stderr")
    mock_process.returncode = 0
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)

    result = await adapter.execute(["echo", "hello"])

    assert result.tool_name == "echo"
    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout == "hello stdout"
    assert result.stderr == "hello stderr"
    assert result.duration_ms >= 0
    assert result.suggestion is None


@pytest.mark.anyio
async def test_subprocess_non_zero_exit(mocker):
    adapter = SubprocessAdapter()

    mock_process = mocker.AsyncMock()
    mock_process.communicate.return_value = (b"", b"error details")
    mock_process.returncode = 1
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)

    result = await adapter.execute(["false"])

    assert result.tool_name == "false"
    assert result.success is False
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "error details"
    assert result.duration_ms >= 0


@pytest.mark.anyio
async def test_subprocess_timeout(mocker):
    adapter = SubprocessAdapter()

    mock_process = mocker.AsyncMock()
    mock_process.communicate.side_effect = asyncio.TimeoutError()
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)

    result = await adapter.execute(["sleep", "10"], timeout=0.1)

    assert result.tool_name == "sleep"
    assert result.success is False
    assert result.exit_code == -2
    assert "timed out" in result.suggestion
    mock_process.kill.assert_called_once()


@pytest.mark.anyio
async def test_subprocess_binary_not_found(mocker):
    adapter = SubprocessAdapter()

    mocker.patch(
        "asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError(
            "[Errno 2] No such file or directory: 'non_existent'"
        ),
    )

    result = await adapter.execute(["non_existent"])

    assert result.tool_name == "non_existent"
    assert result.success is False
    assert result.exit_code == -3
    assert "not found" in result.suggestion


@pytest.mark.anyio
async def test_subprocess_path_resolution_with_registry(mocker):
    # Mock resolved tool
    mock_tool = mocker.MagicMock()
    mock_tool.name = "mkvmerge"
    mock_tool.path = Path("C:/Program Files/MKVToolNix/mkvmerge.exe")
    mock_tool.is_available = True

    # Mock tool registry
    mock_registry = mocker.MagicMock()
    mock_registry.get.return_value = mock_tool

    adapter = SubprocessAdapter(tool_registry=mock_registry)

    mock_process = mocker.AsyncMock()
    mock_process.communicate.return_value = (b"mux success", b"")
    mock_process.returncode = 0
    mock_exec = mocker.patch(
        "asyncio.create_subprocess_exec", return_value=mock_process
    )

    result = await adapter.execute(["mkvmerge", "-o", "out.mkv"])

    # Verify create_subprocess_exec was called with absolute path
    mock_exec.assert_called_once_with(
        str(Path("C:/Program Files/MKVToolNix/mkvmerge.exe")),
        "-o",
        "out.mkv",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert result.success is True


@pytest.mark.anyio
async def test_subprocess_os_error(mocker):
    adapter = SubprocessAdapter()

    mocker.patch(
        "asyncio.create_subprocess_exec", side_effect=OSError("permission denied")
    )

    result = await adapter.execute(["restricted"])

    assert result.tool_name == "restricted"
    assert result.success is False
    assert result.exit_code == -4
    assert "execution error" in result.suggestion


@pytest.mark.anyio
async def test_subprocess_invalid_utf8(mocker):
    adapter = SubprocessAdapter()

    mock_process = mocker.AsyncMock()
    mock_process.communicate.return_value = (b"good stdout \xff", b"error \xff")
    mock_process.returncode = 0
    mocker.patch("asyncio.create_subprocess_exec", return_value=mock_process)

    result = await adapter.execute(["echo", "bad"])

    assert result.success is True
    assert "" in result.stdout
    assert "" in result.stderr


def test_subprocess_adapter_imports_isolation():
    adapter_file = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "adapters"
        / "subprocess.py"
    )

    with open(adapter_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                assert root_name in [
                    "typing",
                    "asyncio",
                    "time",
                    "structlog",
                    "src",
                ] or is_stdlib(root_name), f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_name = node.module.split(".")[0]
                assert root_name in [
                    "typing",
                    "asyncio",
                    "time",
                    "structlog",
                    "src",
                ] or is_stdlib(root_name), f"Forbidden import from: {node.module}"


def is_stdlib(module_name: str) -> bool:
    import sys

    if module_name in sys.builtin_module_names:
        return True
    try:
        mod = __import__(module_name)
        file = getattr(mod, "__file__", None)
        if file is None:
            return True
        return "stdlib" in file or "lib" in file.lower() or "python" in file.lower()
    except Exception:
        return False
