import ast
from pathlib import Path


def get_imported_modules(file_path: Path) -> list[str]:
    """Parse a Python file using AST and return all statically imported modules."""
    imports = []
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
    return imports


def test_gui_boundary_integrity() -> None:
    """Enforce strict Hexagonal Architecture boundaries using AST verification.
    
    GUI files must not have static imports of:
    - src.core
    - src.adapters
    - src.hunters
    - src.models (except bootstrap using dynamic loading or explicitly clean paths)
    """
    gui_dir = Path("src/gui")
    if not gui_dir.exists():
        gui_dir = Path(__file__).parents[3] / "src" / "gui"

    assert gui_dir.exists(), f"Could not find src/gui directory at {gui_dir.resolve()}"

    for path in gui_dir.rglob("*.py"):
        if path.name == "__init__.py":
            continue

        imports = get_imported_modules(path)
        rel_path = path.relative_to(gui_dir).as_posix()

        # Strict checks across different layers
        if rel_path == "theme.py":
            for imp in imports:
                assert not imp.startswith("src"), (
                    f"theme.py violates boundary: statically imported '{imp}' (no src imports allowed)"
                )
        elif rel_path == "messages.py":
            for imp in imports:
                assert not imp.startswith("src"), (
                    f"messages.py violates boundary: statically imported '{imp}' (no src imports allowed)"
                )
        else:
            # All other GUI files (including widgets, signals, main_window, bootstrap)
            # must not import core, adapters, hunters, or models statically.
            for imp in imports:
                for forbidden in ("src.core", "src.adapters", "src.hunters", "src.models"):
                    assert not imp.startswith(forbidden), (
                        f"GUI file '{rel_path}' violates boundary: statically imported '{imp}'"
                    )
