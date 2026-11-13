"""End-to-end check of the desktop backend over its real stdio protocol."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.integration.test_phase_a_real_mkv import ASS_TEMPLATE, _make_episode

ROOT = Path(__file__).resolve().parents[2]


class Client:
    def __init__(self, home: Path) -> None:
        env = dict(os.environ, HOME=str(home), APPDATA=str(home / "AppData"))
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "src.sidecar"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        self.next_id = 0
        self.events: list[dict[str, Any]] = []
        self.wait_for("ready")

    def _read(self) -> dict[str, Any]:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        assert line, "backend closed stdout"
        return json.loads(line)  # type: ignore[no-any-return]

    def call(self, method: str, **params: Any) -> Any:
        assert self.proc.stdin is not None
        self.next_id += 1
        request = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        self.proc.stdin.write(json.dumps({**request, "params": params}) + "\n")
        self.proc.stdin.flush()
        while True:
            message = self._read()
            if message.get("id") == self.next_id:
                if "error" in message:
                    raise RuntimeError(message["error"]["message"])
                return message["result"]
            self.events.append(message["params"])

    def wait_for(self, kind: str) -> dict[str, Any]:
        event: dict[str, Any]
        for event in self.events:
            if event.get("type") == kind:
                return event
        while True:
            event = self._read()["params"]
            self.events.append(event)
            if event.get("type") == kind:
                return event

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        self.proc.wait(timeout=30)


def test_unknown_method_returns_an_error(tmp_path: Path) -> None:
    client = Client(tmp_path)
    with pytest.raises(RuntimeError, match="unknown method"):
        client.call("nope")
    client.close()
    assert client.proc.returncode == 0


@pytest.mark.integration
@pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("mkvmerge")),
    reason="needs ffmpeg and mkvmerge",
)
def test_scan_apply_and_undo_through_the_backend(tmp_path: Path) -> None:
    library = tmp_path / "library"
    show = library / "Show"
    show.mkdir(parents=True)
    episode = _make_episode(show)
    (show / "Show - 01.ass").write_text(
        ASS_TEMPLATE.format(text="مرحبا"), encoding="utf-8"
    )
    original = episode.read_bytes()

    client = Client(tmp_path / "home")
    info = client.call("app.info")
    assert info["missing_required_tools"] == []

    config = client.call("config.update", library_path=str(library))
    assert config["library_path"] == str(library)
    shows = client.call("library.shows")
    assert [s["name"] for s in shows] == ["Show"]

    listing = client.call("library.episodes", path=str(show))
    row = listing["episodes"][0]
    assert row["status"] == "ready" and row["subtitle"]["kind"] == "external"

    client.call("run.start", show_path=str(show), episodes=[row["path"]])
    finished = client.wait_for("run.finished")
    assert [e["status"] for e in finished["episodes"]] == ["partial"]
    assert any(e["type"] == "progress" for e in client.events)
    assert episode.read_bytes() != original

    runs = client.call("history.list")
    assert runs[0]["episodes"][0]["restorable"] is True
    totals = client.call("history.undo", run_id=runs[0]["run_id"])
    assert totals["restored"] == 1
    assert episode.read_bytes() == original
    client.close()
