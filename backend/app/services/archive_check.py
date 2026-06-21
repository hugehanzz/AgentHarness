from pathlib import Path

from fastapi import HTTPException


IGNORED_DIRS = {".git", ".idea", ".venv", "dist", "node_modules", "__pycache__"}


def _iter_readmes(root: Path) -> list[Path]:
    readmes: list[Path] = []
    for path in root.rglob("README.md"):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        readmes.append(path)
    return sorted(readmes)


def check_readme_archive(workspace_path: str) -> dict[str, bool | str | list[str]]:
    root = Path(workspace_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="workspace_path must be an existing directory")
    readmes = _iter_readmes(root)
    if not readmes:
        raise HTTPException(status_code=404, detail="README.md not found")

    # This is a lightweight heuristic gate, not a documentation linter. It
    # catches missing archive signals before a task can be considered complete.
    contents = "\n\n".join(readme.read_text(encoding="utf-8") for readme in readmes)
    lower_content = contents.lower()
    return {
        "readme_path": str(root / "README.md") if (root / "README.md").exists() else str(readmes[0]),
        "readme_paths": [str(readme) for readme in readmes],
        "has_acceptance_status": "acceptance" in lower_content or "验收" in contents,
        "has_test_results": "test" in lower_content or "测试" in contents,
        "has_archive_notes": "archive" in lower_content or "归档" in contents,
        "has_next_steps": "next" in lower_content or "下一步" in contents or "后续" in contents,
    }
