def test_public_imports():
    from src.models import (
        SerializablePath,
        FontQuery,
        FontAsset,
        HunterResult,
        AssetLifecycle,
        SubtitleFile,
        SyncResult,
        TrashReceipt,
        MuxJob,
        MuxResult,
        ToolResult,
        EpisodeStatus,
        EpisodeReport,
        PipelineReport,
    )

    assert SerializablePath is not None
    assert FontQuery is not None
    assert FontAsset is not None
    assert HunterResult is not None
    assert AssetLifecycle is not None
    assert SubtitleFile is not None
    assert SyncResult is not None
    assert TrashReceipt is not None
    assert MuxJob is not None
    assert MuxResult is not None
    assert ToolResult is not None
    assert EpisodeStatus is not None
    assert EpisodeReport is not None
    assert PipelineReport is not None
