"""Converter registry and format routing."""

from __future__ import annotations

from ..config import Settings
from .base import DocumentConverter, UnsupportedFormatError
from .mineru import MineruHttpConverter
from .passthrough import MarkdownPassthroughConverter

_CONVERTERS: dict[str, type[DocumentConverter]] = {}


def register_converter(cls: type[DocumentConverter]) -> type[DocumentConverter]:
    name = getattr(cls, "name", None)
    if not name or not isinstance(name, str):
        raise ValueError("converter class must define a non-empty string 'name'")
    _CONVERTERS[name] = cls
    return cls


def list_converters() -> list[str]:
    return sorted(_CONVERTERS)


def build_default_converters(settings: Settings) -> list[DocumentConverter]:
    return [
        MarkdownPassthroughConverter(),
        MineruHttpConverter(
            settings.parser_url,
            timeout=settings.parser_timeout,
            tier=settings.parser_tier,
            token=settings.parser_token,
        ),
    ]


def select_converter(
    converters: list[DocumentConverter], suffix: str, mime: str
) -> DocumentConverter:
    for converter in converters:
        if converter.supports(suffix, mime):
            return converter
    raise UnsupportedFormatError(f"unsupported document format: {suffix or mime}")


register_converter(MarkdownPassthroughConverter)
register_converter(MineruHttpConverter)
