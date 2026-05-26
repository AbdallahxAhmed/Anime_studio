import ast
import os
import sys
from pathlib import Path
import pytest
from src.errors import ToolNotFoundError
from src.adapters.dependency_checker import (
    DependencyChecker,
    BinaryClassification,
    BinarySpec,
    DEFAULT_SPECS,
)


@pytest.fixture
def mock_dirs(tmp_path):
    home = tmp_path / "home"
    prog_files = tmp_path / "Program Files"
    home.mkdir()
    prog_files.mkdir()
    return home, prog_files


def test_discovery_step1_scoop_shim(mock_dirs, mocker):
    mocker.patch("sys.platform", "win32")
    home, prog_files = mock_dirs
    
    # Create shim
    shim_dir = home / "scoop" / "shims"
    shim_dir.mkdir(parents=True)
    shim_file = shim_dir / "ffmpeg.exe"
    shim_file.touch()
    
    mocker.patch("os.access", return_value=True)
    
    checker = DependencyChecker(home_dir=home, program_files_dir=prog_files)
    spec = BinarySpec(
        name="ffmpeg",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="ffmpeg",
        install_instructions="some instructions",
    )
    
    path = checker.discover_one(spec)
    assert path == shim_file


def test_discovery_step2_scoop_app(mock_dirs, mocker):
    mocker.patch("sys.platform", "win32")
    home, prog_files = mock_dirs
    
    # Create app path
    app_dir = home / "scoop" / "apps" / "ffmpeg" / "current" / "bin"
    app_dir.mkdir(parents=True)
    bin_file = app_dir / "ffmpeg.exe"
    bin_file.touch()
    
    mocker.patch("os.access", return_value=True)
    
    checker = DependencyChecker(home_dir=home, program_files_dir=prog_files)
    spec = BinarySpec(
        name="ffmpeg",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="ffmpeg",
        install_instructions="some instructions",
    )
    
    path = checker.discover_one(spec)
    assert path == bin_file


def test_discovery_step3_mpv(mock_dirs, mocker):
    mocker.patch("sys.platform", "win32")
    home, prog_files = mock_dirs
    
    mpv_dir = prog_files / "mpv"
    mpv_dir.mkdir(parents=True)
    ffmpeg_file = mpv_dir / "ffmpeg.exe"
    ffmpeg_file.touch()
    
    mocker.patch("os.access", return_value=True)
    
    checker = DependencyChecker(home_dir=home, program_files_dir=prog_files)
    spec = BinarySpec(
        name="ffmpeg",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="ffmpeg",
        install_instructions="some instructions",
    )
    
    path = checker.discover_one(spec)
    assert path == ffmpeg_file


def test_discovery_step4_win_folder(mock_dirs, mocker):
    mocker.patch("sys.platform", "win32")
    home, prog_files = mock_dirs
    
    target_dir = prog_files / "ffmpeg" / "bin"
    target_dir.mkdir(parents=True)
    ffmpeg_file = target_dir / "ffmpeg.exe"
    ffmpeg_file.touch()
    
    mocker.patch("os.access", return_value=True)
    
    checker = DependencyChecker(home_dir=home, program_files_dir=prog_files)
    spec = BinarySpec(
        name="ffmpeg",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="ffmpeg",
        install_instructions="some instructions",
    )
    
    path = checker.discover_one(spec)
    assert path == ffmpeg_file


def test_discovery_step5_shutil_which(mock_dirs, mocker):
    mocker.patch("sys.platform", "linux")  # linux only has step 5
    home, prog_files = mock_dirs
    
    mocker.patch("shutil.which", return_value="/usr/bin/ffmpeg")
    mocker.patch("os.access", return_value=True)
    mocker.patch("pathlib.Path.is_file", return_value=True)
    
    checker = DependencyChecker(home_dir=home, program_files_dir=prog_files)
    spec = BinarySpec(
        name="ffmpeg",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="ffmpeg",
        install_instructions="some instructions",
    )
    
    path = checker.discover_one(spec)
    assert path == Path("/usr/bin/ffmpeg").resolve()


def test_discovery_non_executable_skipped(mock_dirs, mocker):
    mocker.patch("sys.platform", "win32")
    home, prog_files = mock_dirs
    
    shim_dir = home / "scoop" / "shims"
    shim_dir.mkdir(parents=True)
    shim_file = shim_dir / "ffmpeg.exe"
    shim_file.touch()
    
    # Executable check fails
    mocker.patch("os.access", return_value=False)
    mocker.patch("shutil.which", return_value=None)
    
    checker = DependencyChecker(home_dir=home, program_files_dir=prog_files)
    spec = BinarySpec(
        name="ffmpeg",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="ffmpeg",
        install_instructions="some instructions",
    )
    
    path = checker.discover_one(spec)
    assert path is None


def test_platform_gating_skips_steps(mock_dirs, mocker):
    mocker.patch("sys.platform", "linux")
    home, prog_files = mock_dirs
    
    # Create windows paths that exist in mock
    shim_dir = home / "scoop" / "shims"
    shim_dir.mkdir(parents=True)
    shim_file = shim_dir / "ffmpeg.exe"
    shim_file.touch()
    
    mocker.patch("shutil.which", return_value=None)
    
    checker = DependencyChecker(home_dir=home, program_files_dir=prog_files)
    spec = BinarySpec(
        name="ffmpeg",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="ffmpeg",
        install_instructions="some instructions",
    )
    
    path = checker.discover_one(spec)
    # Should skip scoop shim and find nothing
    assert path is None


def test_discover_all_missing_critical(mock_dirs, mocker):
    home, prog_files = mock_dirs
    mocker.patch("sys.platform", "linux")
    mocker.patch("shutil.which", return_value=None)  # Find nothing
    
    checker = DependencyChecker(home_dir=home, program_files_dir=prog_files)
    
    specs = [
        BinarySpec(
            name="ffmpeg",
            classification=BinaryClassification.CRITICAL,
            win_folder_name="ffmpeg",
            install_instructions="install ffmpeg",
        ),
        BinarySpec(
            name="mkvmerge",
            classification=BinaryClassification.CRITICAL,
            win_folder_name="MKVToolNix",
            install_instructions="install mkv",
        ),
        BinarySpec(
            name="alass",
            classification=BinaryClassification.OPTIONAL,
            win_folder_name="alass",
            install_instructions="install alass",
        ),
    ]
    
    with pytest.raises(ToolNotFoundError) as exc_info:
        checker.discover_all(specs)
        
    error_msg = str(exc_info.value)
    assert "ffmpeg" in error_msg
    assert "mkvmerge" in error_msg
    # Optional should not be in the critical error message list
    assert "alass" not in error_msg
    
    # But alass should still be registered as unavailable in the registry
    assert checker.registry.is_available("alass") is False


def test_discover_all_success(mock_dirs, mocker):
    home, prog_files = mock_dirs
    mocker.patch("sys.platform", "linux")
    
    # Mock which to resolve both
    def mock_which(cmd, mode=os.F_OK | os.X_OK, path=None):
        if cmd == "ffmpeg":
            return "/usr/bin/ffmpeg"
        if cmd == "alass":
            return "/usr/bin/alass"
        return None
        
    mocker.patch("shutil.which", side_effect=mock_which)
    mocker.patch("os.access", return_value=True)
    mocker.patch("pathlib.Path.is_file", return_value=True)
    
    checker = DependencyChecker(home_dir=home, program_files_dir=prog_files)
    specs = [
        BinarySpec(
            name="ffmpeg",
            classification=BinaryClassification.CRITICAL,
            win_folder_name="ffmpeg",
            install_instructions="install ffmpeg",
        ),
        BinarySpec(
            name="alass",
            classification=BinaryClassification.OPTIONAL,
            win_folder_name="alass",
            install_instructions="install alass",
        ),
    ]
    
    registry = checker.discover_all(specs)
    assert registry.is_available("ffmpeg") is True
    assert registry.is_available("alass") is True
    assert registry.get("ffmpeg").path == Path("/usr/bin/ffmpeg").resolve()
    assert registry.get("alass").path == Path("/usr/bin/alass").resolve()


def test_dependency_checker_imports_isolation():
    checker_file = Path(__file__).parent.parent.parent.parent / "src" / "adapters" / "dependency_checker.py"
    
    with open(checker_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                assert root_name in ["typing", "shutil", "sys", "os", "enum", "pathlib", "pydantic", "structlog", "src"] or is_stdlib(root_name), f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_name = node.module.split(".")[0]
                assert root_name in ["typing", "shutil", "sys", "os", "enum", "pathlib", "pydantic", "structlog", "src"] or is_stdlib(root_name), f"Forbidden import from: {node.module}"


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
