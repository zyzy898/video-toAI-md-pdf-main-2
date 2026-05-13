"""LLM client abstraction.

This package exposes a capability-based client interface on top of different
LLM providers (Ark, OpenAI-compatible, ...). Business code should import from
here instead of calling provider SDKs directly.
"""

from .base import (
    Capability,
    LLMClient,
    ProviderError,
    ProviderAuthError,
    ProviderFeatureUnsupportedError,
    ProviderRequestError,
)
from .factory import build_llm_client, resolve_provider

__all__ = [
    "Capability",
    "LLMClient",
    "ProviderError",
    "ProviderAuthError",
    "ProviderFeatureUnsupportedError",
    "ProviderRequestError",
    "build_llm_client",
    "resolve_provider",
]
