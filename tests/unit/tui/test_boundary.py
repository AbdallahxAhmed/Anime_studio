import ast
from pathlib import Path


def test_tui_boundary_compliance():
    """Verify src/tui/ (excluding bootstrap.py) is a pure presentation layer.

    Ensures zero direct imports of:
    - src.adapters
    - src.hunters
    - subprocess
    - httpx
    - shutil
    - os/os.path

    And ensures zero direct calls to open().
    """
    src_dir = Path(__file__).parent.parent.parent.parent / "src"
    tui_dir = src_dir / "tui"

    assert tui_dir.exists(), f"tui directory not found at {tui_dir}"

    forbidden_modules = [
        "src.adapters",
        "src.hunters",
        "subprocess",
        "httpx",
        "shutil",
        "os",
    ]

    for py_file in tui_dir.rglob("*.py"):
        # Skip composition root
        if py_file.name == "bootstrap.py":
            continue

        with open(py_file, "r", encoding="utf-8") as f:
            content = f.read()
            tree = ast.parse(content)

        for node in ast.walk(tree):
            # Check import statements (e.g. import subprocess)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_modules:
                        assert (
                            not alias.name == forbidden
                            and not alias.name.startswith(forbidden + ".")
                        ), (
                            f"Boundary Violation: {py_file.relative_to(src_dir.parent)} "
                            f"imports forbidden module '{alias.name}'"
                        )

            # Check import from statements (e.g. from src.adapters.subprocess import ...)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_modules:
                        assert (
                            not node.module == forbidden
                            and not node.module.startswith(forbidden + ".")
                        ), (
                            f"Boundary Violation: {py_file.relative_to(src_dir.parent)} "
                            f"imports from forbidden module '{node.module}'"
                        )

            # Check function calls (e.g. open())
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id != "open", (
                        f"Boundary Violation: {py_file.relative_to(src_dir.parent)} "
                        f"calls forbidden function 'open()' directly"
                    )
