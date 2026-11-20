"""Retrieval layer: unified interface over interchangeable engines."""

from .interface import RetrievalEngine, RetrievalHit, RetrievalResponse, RetrievalService

__all__ = ["RetrievalEngine", "RetrievalHit", "RetrievalResponse", "RetrievalService"]
