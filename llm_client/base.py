"""Capability-based LLM client interface and shared error types.

The VideoAnalyzerAgent only depends on this abstraction; concrete providers
(Ark, OpenAI-compatible) implement it. Each provider explicitly advertises
which capabilities it supports and raises ProviderFeatureUnsupportedError
for the rest, so upstream code can degrade gracefully instead of 500'ing.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class Capability(str, Enum):
    """Stable capability identifiers used by clients and routes."""

    CHAT_COMPLETIONS = "chat_completions"
    # responses.create + input_video + file_id (Ark-specific today).
    VIDEO_UNDERSTANDING = "video_understanding"
    # files.create + wait_for_processing (Ark-specific today).
    FILE_UPLOAD = "file_upload"
    # responses.create + tools=[{"type": "web_search"}] (Ark-specific today).
    WEB_SEARCH_TOOL = "web_search_tool"


class ProviderError(RuntimeError):
    """Base class for provider-side errors surfaced to callers."""

    code: str = "provider_error"


class ProviderAuthError(ProviderError):
    code = "risk_model_auth_failed"


class ProviderRequestError(ProviderError):
    code = "provider_request_error"

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ProviderFeatureUnsupportedError(ProviderError):
    """Raised when the active provider cannot fulfil a given capability."""

    code = "provider_feature_unsupported"

    def __init__(
        self,
        *,
        provider: str,
        capability: Capability,
        hint: str = "",
    ):
        message = (
            f"当前模型平台 '{provider}' 不支持能力 '{capability.value}'"
            + (f"，{hint}" if hint else "")
        )
        super().__init__(message)
        self.provider = provider
        self.capability = capability
        self.hint = hint


class LLMClient(ABC):
    """Abstract LLM client. Concrete subclasses wrap a single provider."""

    provider: str = "unknown"
    model: str = ""
    base_url: str = ""

    # ------------------------------------------------------------------
    # Capability declaration
    # ------------------------------------------------------------------
    def supports(self, capability: Capability) -> bool:
        return capability in self._capabilities()

    @abstractmethod
    def _capabilities(self) -> set[Capability]:  # pragma: no cover - trivial
        ...

    # ------------------------------------------------------------------
    # Shared retry helper (kept here so every provider shares the policy).
    # ------------------------------------------------------------------
    async def _call_with_retry(
        self,
        api_func: Callable[[], Any],
        *,
        max_retries: int = 5,
        rate_limit_token: str = "429",
    ) -> Any:
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                return await api_func()
            except Exception as exc:  # noqa: BLE001 - re-raised below
                last_exc = exc
                err_text = str(exc)
                if rate_limit_token in err_text and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    logging.warning(
                        "[LLMClient] 请求频率过快，等待 %ss 后重试 (%s/%s): %s",
                        wait_time,
                        attempt + 1,
                        max_retries,
                        err_text[:200],
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise
        # Should not reach here.
        if last_exc is not None:
            raise last_exc
        raise ProviderRequestError("API call failed with no response")

    # ------------------------------------------------------------------
    # Required capability: plain text chat completion.
    # ------------------------------------------------------------------
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Return assistant text content (already stripped)."""

    # ------------------------------------------------------------------
    # Optional capabilities. Default: raise ProviderFeatureUnsupportedError.
    # Providers override only what they can honour.
    # ------------------------------------------------------------------
    async def upload_video_file(
        self,
        video_path: str,
        *,
        fps: float = 1.0,
    ) -> str:
        raise ProviderFeatureUnsupportedError(
            provider=self.provider,
            capability=Capability.FILE_UPLOAD,
            hint="请切换到支持视频文件上传的模型平台（例如火山 Ark）。",
        )

    async def analyze_video(
        self,
        *,
        file_id: str,
        system_prompt: str,
        user_text: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        raise ProviderFeatureUnsupportedError(
            provider=self.provider,
            capability=Capability.VIDEO_UNDERSTANDING,
            hint="当前平台不支持视频理解，请切换为字幕分析模式或改用支持的平台。",
        )

    async def responses_with_tools(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        raise ProviderFeatureUnsupportedError(
            provider=self.provider,
            capability=Capability.WEB_SEARCH_TOOL,
            hint="当前平台不支持工具调用（如联网搜索），请关闭该选项或切换平台。",
        )

    async def aclose(self) -> None:  # pragma: no cover - provider specific
        return None
