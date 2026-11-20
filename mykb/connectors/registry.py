"""Connector registry: registration and discovery of data-source connectors."""

from __future__ import annotations

from typing import Any

from .base import Connector

_REGISTRY: dict[str, type[Connector]] = {}


def register_connector(cls: type[Connector]) -> type[Connector]:
    """Register a connector class under its ``name`` attribute."""
    name = getattr(cls, "name", None)
    if not name or not isinstance(name, str):
        raise ValueError("connector class must define a non-empty string 'name'")
    _REGISTRY[name] = cls
    return cls


def get_connector(name: str) -> type[Connector]:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown connector '{name}', available: {list_connectors()}") from exc


def create_connector(name: str, **config: Any) -> Connector:
    return get_connector(name)(**config)


def list_connectors() -> list[str]:
    return sorted(_REGISTRY)


from . import markdown_dir  # noqa: F401  (register built-in connectors)
