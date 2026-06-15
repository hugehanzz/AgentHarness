from pydantic import BaseModel


class FilesystemEntry(BaseModel):
    name: str
    path: str
    type: str = "directory"


class FilesystemRoots(BaseModel):
    roots: list[FilesystemEntry]


class FilesystemListResult(BaseModel):
    path: str
    parent_path: str | None
    entries: list[FilesystemEntry]
