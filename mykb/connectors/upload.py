"""Local upload connector.

Uploaded Markdown (or Markdown extracted from a zip) is staged in a temporary
directory and normalized exactly like the markdown-directory connector.
"""

from __future__ import annotations

from .markdown_dir import MarkdownDirConnector
from .registry import register_connector


@register_connector
class UploadDirConnector(MarkdownDirConnector):
    name = "upload"
    source_type = "源数据"
