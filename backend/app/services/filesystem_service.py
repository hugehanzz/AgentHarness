import string
from pathlib import Path

from fastapi import HTTPException

from app.schemas.filesystem import FilesystemEntry, FilesystemListResult, FilesystemRoots


def list_roots() -> FilesystemRoots:
    roots: list[FilesystemEntry] = []
    for drive in string.ascii_uppercase:
        path = Path(f"{drive}:\\")
        if path.exists():
            roots.append(FilesystemEntry(name=f"{drive}:\\", path=str(path)))
    return FilesystemRoots(roots=roots)


def list_directories(path: str) -> FilesystemListResult:
    current = Path(path).expanduser().resolve()
    if not current.exists() or not current.is_dir():
        raise HTTPException(status_code=400, detail="path must be an existing directory")

    entries: list[FilesystemEntry] = []
    try:
        children = sorted(
            [child for child in current.iterdir() if child.is_dir()],
            key=lambda item: item.name.lower(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="permission denied") from exc

    for child in children:
        if child.name.startswith("$"):
            continue
        entries.append(FilesystemEntry(name=child.name, path=str(child)))

    parent = current.parent if current.parent != current else None
    return FilesystemListResult(
        path=str(current),
        parent_path=str(parent) if parent else None,
        entries=entries,
    )
