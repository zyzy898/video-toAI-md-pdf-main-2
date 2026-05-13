"""OpenAI-compatible LLM client.

Speaks plain `POST {base_url}/chat/completions` with Bearer auth. Designed for
OpenAI, DeepSeek, Qwen DashScope, and any other vendor that exposes the OpenAI
chat completions shape. Intentionally does not pull in the `openai` SDK: this
minimises the blast radius (async runtime, dependency surface) and matches the
project's existing urllib-based HTTP style.

Capabilities:
    - CHAT_COMPLETIONS: supported
    - FILE_UPLOAD / VIDEO_UNDERSTANDING / WEB_SEARCH_TOOL: not supported
      (will raise ProviderFeatureUnsupportedError, callers should degrade).
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .base import (
    Capability,
    LLMClient,
    ProviderAuthError,
    ProviderRequestError,
)


_AUTH_HINTS = (
    "invalid api key",
    "authentication fails",
    "api key format is incorrect",
    "incorrect api key provided",
    "apikey-error",
    "unauthorized",
)


class OpenAICompatibleLLMClient(LLMClient):
    """Generic OpenAI-compatible client (chat completions only)."""

    provider = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider: str = "openai_compatible",
        request_timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider or "openai_compatible"
        self.request_timeout = float(request_timeout or 60.0)

    def _capabilities(self) -> set[Capability]:
        return {Capability.CHAT_COMPLETIONS}

    # ------------------------------------------------------------------
    # HTTP helpers (run inside a thread so we don't block the event loop).
    # ------------------------------------------------------------------
    def _post_chat_completions(
        self, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="ignore") or str(exc)
            status = getattr(exc, "code", None)
            if status in (401, 403) or self._looks_like_auth_error(error_text):
                raise ProviderAuthError(
                    f"模型鉴权失败（HTTP {status}）: {error_text[:240]}"
                ) from exc
            raise ProviderRequestError(error_text, status_code=status) from exc
        except Exception as exc:  # noqa: BLE001 - network exception
            raise ProviderRequestError(str(exc)) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderRequestError(f"模型返回非 JSON: {raw[:300]}") from exc

        if not isinstance(data, dict):
            raise ProviderRequestError(f"模型返回格式异常: {raw[:300]}")
        if data.get("error") and not data.get("choices"):
            message = self._extract_error_message(data)
            if self._looks_like_auth_error(message):
                raise ProviderAuthError(message)
            raise ProviderRequestError(message)
        return data

    @staticmethod
    def _extract_error_message(data: Dict[str, Any]) -> str:
        err = data.get("error")
        if isinstance(err, dict):
            for key in ("message", "msg", "error"):
                value = err.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return json.dumps(err, ensure_ascii=False)
        if isinstance(err, str):
            return err
        return "provider returned error"

    @staticmethod
    def _looks_like_auth_error(message: str) -> bool:
        text = str(message or "").lower()
        return any(hint in text for hint in _AUTH_HINTS)

    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderRequestError(
                f"模型返回格式异常 (no choices): {json.dumps(data)[:240]}"
            )
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise ProviderRequestError(
                f"模型返回格式异常 (no message): {json.dumps(data)[:240]}"
            )
        content = message.get("content", "")
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            content = "\n".join(parts)
        return str(content or "").strip()

    # Capability implementations ----------------------------------------------
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        temp = float(0.2 if temperature is None else temperature)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
        }
        if extra:
            # Let callers forward extra fields (e.g. response_format, top_p).
            for key, value in extra.items():
                if key not in payload:
                    payload[key] = value

        async def call_api() -> Dict[str, Any]:
            return await asyncio.to_thread(self._post_chat_completions, payload)

        data = await self._call_with_retry(call_api)
        return self._extract_content(data)

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        logging.debug("[OpenAICompatibleLLMClient] aclose called; no resources held.")
        return None


__all__ = ["OpenAICompatibleLLMClient"]
