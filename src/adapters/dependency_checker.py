import os
import sys
import shutil
from enum import StrEnum
from pathlib import Path
from typing import Dict, List, Sequence
from pydantic import BaseModel, ConfigDict
import structlog

from src.errors import ToolNotFoundError

logger = structlog.get_logger()


class BinaryClassification(StrEnum):
    CRITICAL = "critical"
    OPTIONAL = "optional"


class BinarySpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    classification: BinaryClassification
    win_folder_name: str
    install_instructions: str


class ResolvedTool(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    path: Path
    classification: BinaryClassification
    is_available: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ResolvedTool] = {}

    def register(self, tool: ResolvedTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ResolvedTool | None:
        return self._tools.get(name)

    def is_available(self, name: str) -> bool:
        tool = self.get(name)
        return tool is not None and tool.is_available

    def __contains__(self, name: str) -> bool:
        return self.is_available(name)

    def all_tools(self) -> List[ResolvedTool]:
        return list(self._tools.values())


DEFAULT_SPECS = [
    BinarySpec(
        name="ffmpeg",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="ffmpeg",
        install_instructions="Install FFmpeg via Scoop: 'scoop install ffmpeg' or download from https://ffmpeg.org",
    ),
    BinarySpec(
        name="mkvmerge",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="MKVToolNix",
        install_instructions="Install MKVToolNix via Scoop: 'scoop install mkvtoolnix' or download from https://mkvtoolnix.download",
    ),
    BinarySpec(
        name="mkvextract",
        classification=BinaryClassification.CRITICAL,
        win_folder_name="MKVToolNix",
        install_instructions="Install MKVToolNix via Scoop: 'scoop install mkvtoolnix' or download from https://mkvtoolnix.download",
    ),
    BinarySpec(
        name="alass",
        classification=BinaryClassification.OPTIONAL,
        win_folder_name="alass",
        install_instructions="Install alass via Scoop: 'scoop install alass' or download from https://github.com/kaigi/alass",
    ),
    BinarySpec(
        name="ots-sanitize",
        classification=BinaryClassification.OPTIONAL,
        win_folder_name="ots",
        install_instructions="Install ots-sanitize or download from https://github.com/khaledhosny/ots",
    ),
]


class DependencyChecker:
    def __init__(
        self,
        home_dir: Path | None = None,
        program_files_dir: Path | None = None,
    ) -> None:
        self.home_dir = home_dir or Path.home()
        self.program_files_dir = program_files_dir or Path("C:\\Program Files")
        self.registry = ToolRegistry()

    def discover_one(self, spec: BinarySpec) -> Path | None:
        if sys.platform == "win32":
            # Step 0: Portable tool discovery adjacent to executable or in tools/ folder
            exe_dir = (
                Path(sys.executable).parent
                if getattr(sys, "frozen", False)
                else Path.cwd()
            )
            portable_paths = [
                exe_dir / f"{spec.name}.exe",
                exe_dir / "tools" / f"{spec.name}.exe",
                exe_dir / "tools" / spec.win_folder_name / f"{spec.name}.exe",
            ]
            for p in portable_paths:
                if p.is_file() and os.access(p, os.X_OK):
                    return p

            # Step 1: Scoop shim
            shim_path = self.home_dir / "scoop" / "shims" / f"{spec.name}.exe"
            if shim_path.is_file() and os.access(shim_path, os.X_OK):
                return shim_path

            # Step 2: Scoop app recursive discovery under apps/name/current/
            scoop_app_dir = self.home_dir / "scoop" / "apps" / spec.name / "current"
            if scoop_app_dir.is_dir():
                for p in scoop_app_dir.rglob(f"{spec.name}.exe"):
                    if p.is_file() and os.access(p, os.X_OK):
                        return p

            # Step 3: C:\Program Files\mpv\<tool>.exe
            mpv_path = self.program_files_dir / "mpv" / f"{spec.name}.exe"
            if mpv_path.is_file() and os.access(mpv_path, os.X_OK):
                return mpv_path

            # Step 4: C:\Program Files\<win_folder_name>\**\<tool>.exe
            target_dir = self.program_files_dir / spec.win_folder_name
            if target_dir.is_dir():
                for p in target_dir.rglob(f"{spec.name}.exe"):
                    if p.is_file() and os.access(p, os.X_OK):
                        return p

        # Step 5: shutil.which (runs on all platforms)
        which_name = f"{spec.name}.exe" if sys.platform == "win32" else spec.name
        resolved_which = shutil.which(spec.name) or shutil.which(which_name)
        if resolved_which:
            resolved_path = Path(resolved_which).resolve()
            if resolved_path.is_file() and os.access(resolved_path, os.X_OK):
                return resolved_path

        return None

    def discover_all(self, specs: Sequence[BinarySpec] = DEFAULT_SPECS) -> ToolRegistry:
        missing_critical: List[str] = []
        instructions: List[str] = []

        for spec in specs:
            resolved_path = self.discover_one(spec)
            if resolved_path:
                tool = ResolvedTool(
                    name=spec.name,
                    path=resolved_path,
                    classification=spec.classification,
                    is_available=True,
                )
                self.registry.register(tool)
                logger.info(
                    "dependency resolved", name=spec.name, path=str(resolved_path)
                )
            else:
                if spec.classification == BinaryClassification.CRITICAL:
                    missing_critical.append(spec.name)
                    instructions.append(f"- {spec.name}: {spec.install_instructions}")
                else:
                    tool = ResolvedTool(
                        name=spec.name,
                        path=Path(""),
                        classification=spec.classification,
                        is_available=False,
                    )
                    self.registry.register(tool)
                    logger.warning(
                        "optional dependency missing",
                        name=spec.name,
                        instructions=spec.install_instructions,
                    )

        if missing_critical:
            error_msg = "Required external tools are missing:\n" + "\n".join(
                instructions
            )
            raise ToolNotFoundError(error_msg)

        return self.registry
