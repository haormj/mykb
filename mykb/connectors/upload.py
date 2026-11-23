"""Local upload connector.

The connector only stages raw bytes from the task's temporary directory. Format
conversion happens in a separate stage so binary documents never pass through a
text decoder.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from ..conversion.base import SUPPORTED_SUFFIXES, RawDocument


def guess_mime(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


class UploadDirConnector:
    """Read uploaded files and yield raw documents for conversion."""

    name = "upload"
    source_type = "源数据"

    def __init__(
        self,
        source_dir: str | Path,
        *,
        base_uri: str | None = None,
        source_type: str | None = None,
    ) -> None:
        self.source_dir = Path(source_dir)
        self.base_uri = base_uri.rstrip("/") if base_uri else None
        if source_type:
            self.source_type = source_type

    def resource_for(self, key: str) -> str:
        if self.base_uri:
            return f"{self.base_uri}/{key}"
        return key

    def sync(self) -> list[RawDocument]:
        documents: list[RawDocument] = []
        for path in sorted(self.source_dir.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES:
                continue
            relative = path.relative_to(self.source_dir).as_posix()
            documents.append(
                RawDocument(
                    key=relative,
                    name=path.name,
                    data=path.read_bytes(),
                    mime=guess_mime(path.name),
                    suffix=suffix,
                )
            )
        return documents
