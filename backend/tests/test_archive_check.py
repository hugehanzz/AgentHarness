from app.services.archive_check import check_readme_archive


def test_check_readme_archive_scans_multiple_readmes(tmp_path):
    (tmp_path / "README.md").write_text("验收：已通过\n后续：无", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "README.md").write_text("测试：npm run build\n归档：前端完成", encoding="utf-8")

    result = check_readme_archive(str(tmp_path))

    assert result["has_acceptance_status"] is True
    assert result["has_test_results"] is True
    assert result["has_archive_notes"] is True
    assert result["has_next_steps"] is True
    assert len(result["readme_paths"]) == 2


def test_check_readme_archive_ignores_dependency_readmes(tmp_path):
    (tmp_path / "README.md").write_text("验收：已通过", encoding="utf-8")
    dependency_dir = tmp_path / "node_modules" / "pkg"
    dependency_dir.mkdir(parents=True)
    (dependency_dir / "README.md").write_text("test archive next", encoding="utf-8")

    result = check_readme_archive(str(tmp_path))

    assert result["readme_paths"] == [str(tmp_path / "README.md")]
    assert result["has_test_results"] is False
