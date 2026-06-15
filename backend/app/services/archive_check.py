from pathlib import Path

from fastapi import HTTPException


def check_readme_archive(workspace_path: str) -> dict[str, bool | str]:
    root = Path(workspace_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="workspace_path must be an existing directory")
    readme = root / "README.md"
    if not readme.exists():
        raise HTTPException(status_code=404, detail="README.md not found")
    content = readme.read_text(encoding="utf-8")
    return {
        "readme_path": str(readme),
        "has_acceptance_status": "acceptance" in content.lower() or "验收" in content,
        "has_test_results": "test" in content.lower() or "测试" in content,
        "has_next_steps": "next" in content.lower() or "下一步" in content,
    }
