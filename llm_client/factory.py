"""Provider resolution + client factory.

Resolution order:
    1) explicit provider_hint argument
    2) MODEL_PROVIDER environment variable
    3) base_url heuristic (volces.com / bytedance => ark; openai.com => openai;
       anything else => openai_compatible)

The factory always returns an LLMClient; it never silently returns None.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlparse

from .base import LLMClient


_ARK_HOST_HINTS = (
    "volces.com",
    "volcengineapi.com",
    "bytedance.com",
)
_OPENAI_HOST_HINTS = (
    "api.openai.com",
)


def resolve_provider(
    *,
    provider_hint: Optional[str] = None,
    base_url: str = "",
) -> str:
    """Return one of: 'ark', 'openai', 'openai_compatible'."""

    hint = str(provider_hint or "").strip().lower()
    if hint in {"ark", "openai", "openai_compatible"}:
        return hint

    env_hint = str(os.getenv("MODEL_PROVIDER", "")).strip().lower()
    if env_hint in {"ark", "openai", "openai_compatible"}:
        return env_hint

    host = ""
    try:
        parsed = urlparse(base_url)
        host = (parsed.netloc or "").lower()
    except Exception:  # pragma: no cover - defensive
        host = ""

    if any(token in host for token in _ARK_HOST_HINTS):
        return "ark"
    if any(token in host for token in _OPENAI_HOST_HINTS):
        return "openai"
    return "openai_compatible"


def build_llm_client(
    *,
    api_key: str,
    base_url: str,
    model: str,
    provider_hint: Optional[str] = None,
) -> LLMClient:
    """Construct the appropriate concrete LLM client."""

    if not api_key:
        raise ValueError("API Key 未设置，无法构建 LLM 客户端")
    base_url = str(base_url or "").strip() or "https://ark.cn-beijing.volces.com/api/v3"
    model = str(model or "").strip() or "doubao-seed-2-0-pro-260215"

    provider = resolve_provider(provider_hint=provider_hint, base_url=base_url)

    if provider == "ark":
        try:
            from .ark_client import ArkLLMClient
        except Exception as exc:  # pragma: no cover - SDK missing
            logging.warning(
                "[llm_client] Ark SDK 不可用，回退到 openai_compatible: %s",
                exc,
            )
            from .openai_compat_client import OpenAICompatibleLLMClient

            return OpenAICompatibleLLMClient(
                api_key=api_key,
                base_url=base_url,
                model=model,
                provider="openai_compatible",
            )
        return ArkLLMClient(api_key=api_key, base_url=base_url, model=model)

    from .openai_compat_client import OpenAICompatibleLLMClient

    return OpenAICompatibleLLMClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider=provider,
    )


__all__ = ["build_llm_client", "resolve_provider"]
