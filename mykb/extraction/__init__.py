"""Data extraction: AI drafting, git review, and lineage."""

from .drafter import Drafter
from .lineage import build_source_entries, trace_dependents
from .llm import FakeLLM, LLMClient, OpenAICompatibleLLM, get_default_llm
from .review import GitReview, ReviewResult, stamp_verified

__all__ = [
    "Drafter",
    "FakeLLM",
    "GitReview",
    "LLMClient",
    "OpenAICompatibleLLM",
    "ReviewResult",
    "build_source_entries",
    "get_default_llm",
    "stamp_verified",
    "trace_dependents",
]
