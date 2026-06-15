from pathlib import Path

from app.services.filesystem_service import list_directories


def test_list_directories_returns_only_directories(tmp_path: Path):
    (tmp_path / "folder-b").mkdir()
    (tmp_path / "folder-a").mkdir()
    (tmp_path / "file.txt").write_text("ignored", encoding="utf-8")

    result = list_directories(str(tmp_path))

    assert [entry.name for entry in result.entries] == ["folder-a", "folder-b"]
    assert result.path == str(tmp_path.resolve())
