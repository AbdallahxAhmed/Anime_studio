import ast
from pathlib import Path
from typing import Sequence
import httpx
from src.ports.subprocess import SubprocessPort
from src.ports.http_client import HttpClientPort
from src.models.tool_result import ToolResult


class DummySubprocess:
    async def execute(
        self,
        args: Sequence[str],
        timeout: float | None = None,
    ) -> ToolResult:
        return ToolResult(
            tool_name=args[0],
            success=True,
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_ms=1.0,
        )


class DummyHttpClient:
    def create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient()


def test_protocols_runtime_checkable():
    assert isinstance(DummySubprocess(), SubprocessPort)
    assert isinstance(DummyHttpClient(), HttpClientPort)


def test_ports_imports_isolation():
    ports_dir = Path(__file__).parent.parent.parent.parent / "src" / "ports"

    for py_file in ports_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        with open(py_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".")[0]
                    # Allowed external packages for ports: standard library, typing, httpx
                    assert root_name in [
                        "typing",
                        "httpx",
                        "src",
                        "models",
                    ] or is_stdlib(root_name), (
                        f"Forbidden import: {alias.name} in {py_file.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_name = node.module.split(".")[0]
                    assert root_name in [
                        "typing",
                        "httpx",
                        "src",
                        "models",
                    ] or is_stdlib(root_name), (
                        f"Forbidden import from: {node.module} in {py_file.name}"
                    )


def is_stdlib(module_name: str) -> bool:
    # A simple checker for stdlib modules
    import sys

    if module_name in sys.builtin_module_names:
        return True

    # Try importing and check if file path contains standard library path
    try:
        mod = __import__(module_name)
        file = getattr(mod, "__file__", None)
        if file is None:
            return True
        return "stdlib" in file or "lib" in file.lower() or "python" in file.lower()
    except Exception:
        return False
