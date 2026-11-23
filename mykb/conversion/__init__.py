"""Document conversion layer (raw bytes -> markdown + assets)."""

from .base import (
    ALLOWED_ASSET_SUFFIXES,
    MARKDOWN_SUFFIXES,
    SUPPORTED_SUFFIXES,
    Asset,
    ConversionAuthError,
    ConversionError,
    ConversionLimitError,
    ConversionNotConfiguredError,
    ConversionResult,
    ConversionUnavailableError,
    DocumentConverter,
    RawDocument,
    UnsupportedFormatError,
)
from .mineru import MineruHttpConverter
from .passthrough import MarkdownPassthroughConverter
from .registry import (
    build_default_converters,
    list_converters,
    register_converter,
    select_converter,
)
from .service import ConverterService

__all__ = [
    "ALLOWED_ASSET_SUFFIXES",
    "MARKDOWN_SUFFIXES",
    "SUPPORTED_SUFFIXES",
    "Asset",
    "ConversionAuthError",
    "ConversionError",
    "ConversionLimitError",
    "ConversionNotConfiguredError",
    "ConversionResult",
    "ConversionUnavailableError",
    "ConverterService",
    "DocumentConverter",
    "MarkdownPassthroughConverter",
    "MineruHttpConverter",
    "RawDocument",
    "UnsupportedFormatError",
    "build_default_converters",
    "list_converters",
    "register_converter",
    "select_converter",
]
