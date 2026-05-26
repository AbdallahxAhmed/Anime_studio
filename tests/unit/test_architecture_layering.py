import ast
from pathlib import Path


def test_hexagonal_architecture_layering():
    src_dir = Path(__file__).parent.parent.parent / "src"

    forbidden_prefixes = ["src.core", "src.hunters", "src.tui", "src.main"]

    # Files to inspect
    target_dirs = [src_dir / "ports", src_dir / "adapters"]

    for target_dir in target_dirs:
        if not target_dir.exists():
            continue

        for py_file in target_dir.rglob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in forbidden_prefixes:
                            assert not alias.name.startswith(forbidden), (
                                f"Hexagonal Violation: {py_file.relative_to(src_dir.parent)} "
                                f"imports forbidden module '{alias.name}'"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        # Check direct imports like from src.core import ...
                        for forbidden in forbidden_prefixes:
                            assert not node.module.startswith(forbidden), (
                                f"Hexagonal Violation: {py_file.relative_to(src_dir.parent)} "
                                f"imports from forbidden module '{node.module}'"
                            )

                        # Also handle relative imports if any
                        if node.level > 0:
                            # Relative imports are allowed within the package, but let's make sure they don't break boundaries.
                            pass
