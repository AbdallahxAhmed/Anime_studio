from datetime import datetime, timezone
import pytest

from src.adapters.filesystem import FilesystemAdapter
from src.models.trash import TrashReceipt


@pytest.mark.anyio
async def test_filesystem_adapter_operations(tmp_path):
    adapter = FilesystemAdapter()

    # Test ensure_directory
    test_dir = tmp_path / "subdir" / "deep"
    assert not test_dir.exists()
    await adapter.ensure_directory(test_dir)
    assert test_dir.is_dir()

    # Test write_file_atomic
    test_file = test_dir / "file.txt"
    content = "Hello, Anime Studio!"
    await adapter.write_file_atomic(test_file, content)
    assert test_file.is_file()
    assert test_file.read_text(encoding="utf-8") == content

    # Test replace_file
    source_file = test_dir / "source.txt"
    source_file.write_text("New Content", encoding="utf-8")
    await adapter.replace_file(source_file, test_file)
    assert not source_file.exists()
    assert test_file.read_text(encoding="utf-8") == "New Content"

    # Test move_to_trash
    receipt = TrashReceipt(
        original_path=test_file,
        trash_path=tmp_path / ".trash" / "file.txt",
        deletion_time=datetime.now(timezone.utc),
        expiration_time=datetime.now(timezone.utc),
    )
    await adapter.move_to_trash(test_file, receipt)
    assert not test_file.exists()
    assert receipt.trash_path.is_file()
    assert receipt.trash_path.read_text(encoding="utf-8") == "New Content"
