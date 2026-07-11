"""Ark LLM client (火山引擎).

Wraps volcenginesdkarkruntime.AsyncArk and advertises the richest capability
set: chat completions, video understanding, file upload, and web_search tool.
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
    ProviderFeatureUnsupportedError,
    ProviderRequestError,
    ToolResponse,
)


class ArkLLMClient(LLMClient):
    """Ark client. Supports all capabilities currently used by the project."""

    provider = "ark"

    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        # Import lazily so modules loaded by tests without the Ark SDK still work.
        from volcenginesdkarkruntime import AsyncArk

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = AsyncArk(base_url=self.base_url, api_key=self.api_key)

    # Capability advertisement -------------------------------------------------
    def _capabilities(self) -> set[Capability]:
        return {
            Capability.CHAT_COMPLETIONS,
            Capability.VIDEO_UNDERSTANDING,
            Capability.FILE_UPLOAD,
            Capability.WEB_SEARCH_TOOL,
        }

    # Internal helpers ---------------------------------------------------------
    def _chat_completion_http_fallback(
        self, messages: List[Dict[str, Any]], temperature: float
    ) -> str:
        """Direct HTTP POST /chat/completions, used when SDK rejects extra fields."""

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature),
        }
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="ignore")
            raise ProviderRequestError(
                error_text or str(exc), status_code=exc.code
            ) from exc
        except Exception as exc:  # noqa: BLE001 - network exception
            raise ProviderRequestError(str(exc)) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderRequestError(f"模型返回非 JSON: {raw[:300]}") from exc

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderRequestError(f"模型返回格式异常: {raw[:300]}")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    text_parts.append(str(item.get("text", "")))
            content = "\n".join(text_parts)
        return str(content or "").strip()

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        """Extract assistant text from an Ark `responses.create` result."""

        output = getattr(response, "output", None) or []
        for item in output:
            if (
                getattr(item, "role", None) == "assistant"
                and getattr(item, "content", None) is not None
            ):
                for content_item in item.content:
                    text_value = getattr(content_item, "text", None)
                    if text_value:
                        return str(text_value)
        return ""

    @staticmethod
    def _completed_tool_types(response: Any) -> frozenset[str]:
        """Return only tool calls that the provider marked as completed."""

        output = (
            response.get("output", [])
            if isinstance(response, dict)
            else getattr(response, "output", None) or []
        )
        completed: set[str] = set()
        for item in output:
            if isinstance(item, dict):
                item_type = item.get("type")
                status = item.get("status")
            else:
                item_type = getattr(item, "type", None)
                status = getattr(item, "status", None)
            if item_type == "web_search_call" and status == "completed":
                completed.add(item_type)
        return frozenset(completed)

    # Capability implementations ----------------------------------------------
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        temp = float(0.2 if temperature is None else temperature)

        async def call_api() -> Any:
            return await self._client.chat.completions.create(
                model=self.model,
                temperature=temp,
                messages=messages,
            )

        try:
            response = await self._call_with_retry(call_api)
        except Exception as exc:  # noqa: BLE001 - we translate below
            err = str(exc).lower()
            # Some Ark SDK versions silently inject stream_options when the
            # backend does not expect it; fall back to a direct HTTP call.
            if "stream_options" in err and "stream: true" in err:
                return await asyncio.to_thread(
                    self._chat_completion_http_fallback, messages, temp
                )
            raise

        choices = getattr(response, "choices", None) or []
        if choices:
            first = choices[0]
            message = getattr(first, "message", None)
            if message is not None:
                content = getattr(message, "content", None)
                if content:
                    return str(content).strip()
        return ""

    async def upload_video_file(
        self,
        video_path: str,
        *,
        fps: float = 1.0,
    ) -> str:
        try:
            with open(video_path, "rb") as stream:
                file_obj = await self._client.files.create(
                    file=stream,
                    purpose="user_data",
                    preprocess_configs={"video": {"fps": fps}},
                )
            file_id = getattr(file_obj, "id", "")
            if not file_id:
                raise ProviderRequestError("Ark files.create 未返回 file_id")
            await self._client.files.wait_for_processing(file_id)
            return str(file_id)
        except ProviderRequestError:
            raise
        except Exception as exc:  # noqa: BLE001 - translate to provider error
            raise ProviderRequestError(str(exc)) from exc

    async def analyze_video(
        self,
        *,
        file_id: str,
        system_prompt: str,
        user_text: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        async def call_api() -> Any:
            return await self._client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_video", "file_id": file_id},
                            {"type": "input_text", "text": user_text},
                        ],
                    },
                ],
            )

        response = await self._call_with_retry(call_api)
        return self._extract_response_text(response)

    async def responses_with_tools(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        extra: Optional[Dict[str, Any]] = None,
    ) -> ToolResponse:
        async def call_api() -> Any:
            return await self._client.responses.create(
                model=self.model,
                input=messages,
                tools=tools,
            )

        try:
            response = await self._call_with_retry(call_api)
        except Exception as exc:  # noqa: BLE001 - propagate upstream
            logging.warning("[ArkLLMClient] responses.create with tools failed: %s", exc)
            raise
        return ToolResponse(
            self._extract_response_text(response),
            completed_tool_types=self._completed_tool_types(response),
        )

    async def aclose(self) -> None:
        closer = getattr(self._client, "close", None)
        if callable(closer):
            result = closer()
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]


__all__ = ["ArkLLMClient"]
