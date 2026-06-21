import asyncio
import os
import json
import logging
import subprocess
import re
import base64
import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from threading import RLock

from llm_client import (
    Capability,
    LLMClient,
    ProviderFeatureUnsupportedError,
    build_llm_client,
    resolve_provider,
)

try:
    import ffmpeg
except Exception:  # pragma: no cover - 兜底兼容
    ffmpeg = None

from asr import build_transcriber, write_srt_file
from asr.base import TranscriberBackend, TranscriberError

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class VideoAnalyzerAgent:
    DEFAULT_MODEL_NAME = "doubao-seed-2-0-pro-260215"
    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
    DEFAULT_CHAT_TEMPERATURE = 0.2
    SUBTITLE_CACHE_ROOT = (Path(__file__).resolve().parent / "outputs" / ".subtitle_cache").resolve()
    _subtitle_cache_lock = RLock()
    FONT_PATHS = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\SIMSUN.TTC",
        "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
        "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]

    def __init__(
        self,
        api_key: str = None,
        whisper_model: str = "base",
        model_name: str = None,
        model_base_url: str = None,
        provider: str = None,
        llm_client: LLMClient = None,
        transcriber: "TranscriberBackend | None" = None,
    ):
        """
        初始化视频分析AI Agent
        :param api_key: 模型 API Key，None 时从 .env 读取
        :param whisper_model: faster-whisper 模型大小（tiny/base/small/medium/large）
        :param model_name: 模型名称，None 时从 .env 读取
        :param model_base_url: 模型接口 Base URL，None 时从 .env 读取
        :param provider: 可选的 provider 提示（ark / openai / openai_compatible），
            未提供时按 MODEL_PROVIDER 或 base_url 自动路由
        :param llm_client: 可选的 LLMClient 实例（主要用于测试注入）
        :param transcriber: 可选的 :class:`TranscriberBackend` 实例（用于测试注入）。
        """
        load_dotenv()

        if api_key:
            self.api_key = api_key
        else:
            self.api_key = (
                os.getenv("MODEL_API_KEY")
                or os.getenv("ARK_API_KEY")
                or os.getenv("OPENAI_API_KEY")
            )
            if not self.api_key:
                raise ValueError(
                    "API Key 未设置，请在 .env 中配置 MODEL_API_KEY / ARK_API_KEY / OPENAI_API_KEY，或通过参数传入"
                )

        self.base_url = (
            str(model_base_url or "").strip()
            or str(os.getenv("MODEL_BASE_URL", "")).strip()
            or self.DEFAULT_BASE_URL
        )
        self.model = (
            str(model_name or "").strip()
            or str(os.getenv("MODEL_NAME", "")).strip()
            or self.DEFAULT_MODEL_NAME
        )

        if llm_client is not None:
            self.llm_client = llm_client
            self.provider = getattr(llm_client, "provider", "unknown")
        else:
            self.provider = resolve_provider(
                provider_hint=provider,
                base_url=self.base_url,
            )
            self.llm_client = build_llm_client(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
                provider_hint=self.provider,
            )
        # Backwards compatibility: older code paths expected `self.client`
        # to expose the raw provider SDK. Keep it as an alias so any remaining
        # direct access continues to work without crashing immediately.
        self.client = self.llm_client
        self.whisper_model = whisper_model
        self.whisper_threads = self._resolve_whisper_threads()
        self.ffmpeg_cmd = self._prepare_ffmpeg_command()
        if transcriber is not None:
            self.transcriber = transcriber
        else:
            self.transcriber = build_transcriber(
                model_size=str(self.whisper_model or "base"),
                threads=int(self.whisper_threads),
                language="zh",
                ffmpeg_cmd=self.ffmpeg_cmd,
            )
        self.whisper_backend = getattr(self.transcriber, "name", "faster_whisper")
        self._parsed_srt_cache_key: tuple[str, int, int] | None = None
        self._parsed_srt_cache_value: List[Dict[str, Any]] | None = None
        try:
            self.SUBTITLE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logging.warning("字幕缓存目录初始化失败，将回退到直连模式: %s", exc)

    def _resolve_whisper_threads(self) -> int:
        raw_value = str(os.getenv("WHISPER_THREADS", "")).strip()
        default_threads = max(1, min(8, int(os.cpu_count() or 1)))
        if not raw_value:
            return default_threads
        try:
            threads = int(raw_value)
        except (TypeError, ValueError):
            return default_threads
        return max(1, min(16, threads))

    def _prepare_ffmpeg_command(self) -> str:
        """
        优先使用 imageio-ffmpeg 提供的二进制并注入 PATH，
        这样无需手工安装系统级 ffmpeg。
        """
        try:
            import imageio_ffmpeg
        except Exception as exc:
            logging.warning("imageio-ffmpeg 不可用，回退到系统 ffmpeg: %s", exc)
            return "ffmpeg"

        ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        if not ffmpeg_exe.exists():
            logging.warning("imageio-ffmpeg ffmpeg 路径无效，回退到系统 ffmpeg: %s", ffmpeg_exe)
            return "ffmpeg"

        shim_dir = Path(__file__).resolve().parent / ".runtime_bin"
        shim_dir.mkdir(parents=True, exist_ok=True)

        if os.name == "nt":
            shim_path = shim_dir / "ffmpeg.cmd"
            shim_content = f'@echo off\r\n"{ffmpeg_exe}" %*\r\n'
        else:
            shim_path = shim_dir / "ffmpeg"
            shim_content = f'#!/usr/bin/env sh\nexec "{ffmpeg_exe}" "$@"\n'

        existing_content = ""
        if shim_path.exists():
            existing_content = shim_path.read_text(encoding="utf-8", errors="ignore")
        if existing_content != shim_content:
            shim_path.write_text(shim_content, encoding="utf-8")
        if os.name != "nt":
            shim_path.chmod(0o755)

        current_path = os.environ.get("PATH", "")
        path_parts = current_path.split(os.pathsep) if current_path else []
        shim_dir_str = str(shim_dir)
        if shim_dir_str not in path_parts:
            os.environ["PATH"] = shim_dir_str + (os.pathsep + current_path if current_path else "")

        logging.info("ffmpeg 二进制已就绪: %s", ffmpeg_exe)
        return str(ffmpeg_exe)

    def _extract_response_text(self, response) -> str:
        """从模型响应中提取文本内容"""
        for item in response.output:
            if (
                hasattr(item, "role")
                and item.role == "assistant"
                and hasattr(item, "content")
            ):
                for content_item in item.content:
                    if hasattr(content_item, "text"):
                        return content_item.text
        return ""

    async def _call_api_with_retry(self, api_func, *args, **kwargs):
        """Shared retry wrapper for async provider calls.

        Uses :meth:`LLMClient._call_with_retry` under the hood so the policy
        (5 attempts, exponential 10s backoff on 429) is consistent across
        every code path that talks to the model.
        """

        async def _invoke():
            return await api_func(*args, **kwargs)

        return await self.llm_client._call_with_retry(_invoke)

    async def _chat_completion_text(
        self, messages: List[Dict[str, Any]], temperature: float | None = None
    ) -> str:
        """Thin delegate to the active LLM client."""

        return await self.llm_client.chat_completion(
            messages,
            temperature=temperature,
        )

    async def test_model_connection(self) -> Dict[str, Any]:
        """Use a tiny request to validate whether model connection is available."""
        reply = await self._chat_completion_text(
            [
                {"role": "system", "content": "You are a connectivity checker."},
                {"role": "user", "content": "Reply with OK."},
            ]
        )
        return {
            "ok": True,
            "reply": str(reply or "")[:120],
            "model": self.model,
            "base_url": self.base_url,
            "provider": getattr(self.llm_client, "provider", self.provider),
        }

    def _strip_code_fence(self, text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    def _extract_json_fragment(
        self, text: str, opener: str, closer: str
    ) -> Optional[str]:
        start = text.find(opener)
        end = text.rfind(closer)
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start : end + 1]

    def _parse_json_response(self, result: str) -> List[Dict]:
        """解析 JSON 响应"""
        cleaned = self._strip_code_fence(result)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            json_fragment = self._extract_json_fragment(cleaned, "[", "]")
            if not json_fragment:
                raise ValueError(f"无法解析模型返回的JSON格式: {result}")
            parsed = json.loads(json_fragment)

        if not isinstance(parsed, list):
            raise ValueError(f"JSON 格式不是数组: {type(parsed).__name__}")
        return parsed

    def _parse_json_object_response(self, result: str) -> Dict[str, Any]:
        cleaned = self._strip_code_fence(result)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            json_fragment = self._extract_json_fragment(cleaned, "{", "}")
            if not json_fragment:
                raise ValueError(f"无法解析模型返回的JSON对象: {result}")
            parsed = json.loads(json_fragment)

        if not isinstance(parsed, dict):
            raise ValueError(f"JSON 格式不是对象: {type(parsed).__name__}")
        return parsed

    def _parse_timestamp(self, time_str: str) -> int:
        """解析时间字符串为秒数"""
        parts = [int(part) for part in time_str.split(":")]
        if len(parts) == 2:
            minutes, seconds = parts
            return minutes * 60 + seconds
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return hours * 3600 + minutes * 60 + seconds
        raise ValueError(f"不支持的时间格式: {time_str}")

    # ========== Whisper 字幕生成 ==========

    def _build_subtitle_cache_key(
        self,
        video_path: Path,
        cache_identity: Optional[str] = None,
    ) -> str:
        backend_signature = ""
        try:
            backend_signature = self.transcriber.cache_signature()
        except Exception:
            backend_signature = getattr(self.transcriber, "name", "faster_whisper")

        normalized_identity = str(cache_identity or "").strip()
        if normalized_identity:
            raw_key = (
                f"cache_identity:{normalized_identity}|{self.whisper_model}|zh|"
                f"{backend_signature}"
            )
            return hashlib.sha256(raw_key.encode("utf-8", errors="ignore")).hexdigest()

        stat_info = video_path.stat()
        mtime_ns = int(getattr(stat_info, "st_mtime_ns", int(stat_info.st_mtime * 1e9)))
        raw_key = (
            f"{video_path.resolve(strict=False)}|{stat_info.st_size}|{mtime_ns}|"
            f"{self.whisper_model}|zh|{backend_signature}"
        )
        return hashlib.sha256(raw_key.encode("utf-8", errors="ignore")).hexdigest()

    def _try_restore_subtitle_from_cache(
        self,
        video_path: Path,
        target_srt_path: Path,
        cache_identity: Optional[str] = None,
    ) -> bool:
        try:
            cache_key = self._build_subtitle_cache_key(video_path, cache_identity=cache_identity)
        except OSError:
            return False

        cache_path = self.SUBTITLE_CACHE_ROOT / f"{cache_key}.srt"
        with self._subtitle_cache_lock:
            try:
                if not cache_path.exists() or cache_path.stat().st_size <= 0:
                    return False
                target_srt_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cache_path, target_srt_path)
                return target_srt_path.exists() and target_srt_path.stat().st_size > 0
            except OSError:
                return False

    def _save_subtitle_to_cache(
        self,
        video_path: Path,
        srt_path: Path,
        cache_identity: Optional[str] = None,
    ) -> None:
        try:
            cache_key = self._build_subtitle_cache_key(video_path, cache_identity=cache_identity)
        except OSError:
            return

        cache_path = self.SUBTITLE_CACHE_ROOT / f"{cache_key}.srt"
        with self._subtitle_cache_lock:
            try:
                if cache_path.exists() and cache_path.stat().st_size > 0:
                    return
                shutil.copy2(srt_path, cache_path)
            except OSError:
                return

    def generate_subtitles(
        self,
        video_path: str,
        output_dir: str = ".",
        cache_identity: Optional[str] = None,
    ) -> str:
        """
        通过当前配置的 ASR 后端从视频生成 SRT 字幕文件。

        :param video_path: 视频文件路径
        :param output_dir: 字幕输出目录
        :param cache_identity: 跨目录复用字幕缓存的身份标识（如视频 SHA-256）
        :return: 生成的 SRT 文件路径
        """
        video_file = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        srt_filename = video_file.stem + ".srt"
        srt_path = output_dir / srt_filename

        if srt_path.exists() and srt_path.stat().st_size > 0:
            return str(srt_path)
        if self._try_restore_subtitle_from_cache(
            video_file,
            srt_path,
            cache_identity=cache_identity,
        ):
            print(f"字幕缓存命中: {srt_path}")
            return str(srt_path)

        backend_name = getattr(self.transcriber, "name", self.whisper_backend)
        print(
            f"正在使用 {backend_name} ({self.whisper_model}) 生成字幕..."
        )
        try:
            result = self.transcriber.transcribe(video_file, language="zh")
        except TranscriberError as exc:
            raise RuntimeError(f"字幕生成失败: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"字幕生成失败: {exc}") from exc

        write_srt_file(srt_path, result.segments)

        if not srt_path.exists() or srt_path.stat().st_size <= 0:
            raise FileNotFoundError(f"字幕文件未生成: {srt_path}")

        self._save_subtitle_to_cache(video_file, srt_path, cache_identity=cache_identity)
        print(f"字幕已生成: {srt_path}")
        return str(srt_path)

    # ========== 字幕 LLM 同音字纠错（可选增强，上下文感知） ==========

    async def correct_subtitles_with_llm(
        self,
        srt_path: str,
        *,
        glossary: Optional[str] = None,
        batch_size: int = 40,
    ) -> int:
        """对已生成的 SRT 字幕做一次 LLM 上下文同音字纠错并就地回写。

        把字幕按批送给模型，要求"仅修正同音/近音错别字、不得改写语义"，
        并通过长度比例护栏拒绝任何疑似改写，保证不会破坏原意。

        :param srt_path: SRT 文件路径
        :param glossary: 可选的正确术语提示（逗号/空格分隔），辅助模型判断
        :param batch_size: 每次调用模型处理的字幕行数
        :return: 实际被修正的字幕行数
        """
        from asr.subtitle_correct import (
            apply_corrections,
            build_correction_messages,
            chunk_lines,
            parse_correction_response,
        )

        path = Path(srt_path)
        if not path.exists() or path.stat().st_size <= 0:
            return 0

        subtitles = self.parse_srt(srt_path)
        if not subtitles:
            return 0

        texts = [str(sub.get("text", "") or "") for sub in subtitles]
        glossary = glossary or os.getenv("SUBTITLE_CORRECT_GLOSSARY") or None

        async def _correct_batch(batch):
            messages = build_correction_messages(batch, glossary=glossary)
            try:
                reply = await self._chat_completion_text(messages, temperature=0.0)
            except Exception as exc:  # noqa: BLE001 - never block on a bad batch
                logging.warning("[correct_subtitles] 批次纠错调用失败，保留原文: %s", exc)
                return {}
            return parse_correction_response(reply)

        batches = chunk_lines(texts, batch_size=batch_size)
        print(f"正在对 {len(texts)} 行字幕做 LLM 同音字纠错（{len(batches)} 批）...")

        batch_results = await asyncio.gather(
            *(_correct_batch(batch) for batch in batches),
            return_exceptions=True,
        )

        merged: Dict[int, str] = {}
        for item in batch_results:
            if isinstance(item, Exception):
                logging.warning("[correct_subtitles] 批次异常，已跳过: %s", item)
                continue
            if isinstance(item, dict):
                merged.update(item)

        corrected_texts, changed = apply_corrections(texts, merged)
        if changed <= 0:
            print("字幕纠错完成：未发现需要修正的同音字。")
            return 0

        # 收集发生变化的行（带时间戳），用于记录复查日志 + 沉淀热词。
        changes = [
            {
                "time": str(subtitles[i].get("start_time", "") or ""),
                "original": texts[i],
                "corrected": corrected_texts[i],
            }
            for i in range(len(texts))
            if texts[i] != corrected_texts[i]
        ]
        try:
            from asr.correction_log import record_and_learn

            _written, added = record_and_learn(changes, video=Path(srt_path).stem)
            if added:
                print(f"已沉淀 {len(added)} 个新热词到方案A词表: {', '.join(added)}")
        except Exception as exc:  # noqa: BLE001 - logging must never block纠错
            logging.warning("[correct_subtitles] 纠错记录/热词沉淀失败: %s", exc)

        self._rewrite_srt_text(srt_path, subtitles, corrected_texts)
        # 字幕内容变了，让解析缓存失效，下游重新读取纠错后的文本。
        self._parsed_srt_cache_key = None
        self._parsed_srt_cache_value = None
        print(f"字幕纠错完成：共修正 {changed} 行。")
        return changed

    def _rewrite_srt_text(
        self,
        srt_path: str,
        subtitles: List[Dict[str, Any]],
        new_texts: List[str],
    ) -> None:
        """用纠错后的文本就地重写 SRT，保留原有时间轴与序号。"""
        from asr.base import SubtitleSegment
        from asr import write_srt_file

        segments: List[SubtitleSegment] = []
        for sub, text in zip(subtitles, new_texts):
            try:
                start = float(sub.get("start_seconds", 0.0) or 0.0)
                end = self.time_to_seconds(sub.get("end_time", sub.get("start_time", "00:00:00,000")))
            except Exception:
                start = float(sub.get("start_seconds", 0.0) or 0.0)
                end = start
            segments.append(SubtitleSegment(start=start, end=float(end), text=str(text)))
        write_srt_file(Path(srt_path), segments)

    # ========== 字幕分析：识别操作步骤（默认模式，纯文本，便宜） ==========

    async def analyze_subtitles(self, srt_path: str) -> List[Dict]:
        """
        通过分析字幕文本识别操作步骤（Chat Completions API，纯文本调用）
        :param srt_path: SRT字幕文件路径
        :return: 操作步骤列表
        """
        subtitles = self.parse_srt(srt_path)
        subtitle_text = "\n".join(
            [
                f"[{sub['start_time']} --> {sub['end_time']}] {sub['text']}"
                for sub in subtitles
            ]
        )

        system_prompt = """你是一个专业的操作视频分析助手。我会给你一段操作视频的字幕内容（带时间戳），请根据字幕的语义分析出视频中展示的所有操作步骤。

对于每个步骤，请提供：
1. step: 步骤编号（从1开始）
2. time: 该步骤最关键的时间点，格式为 "MM:SS"（选择该步骤中最能代表操作内容的一句话对应的时间）
3. title: 步骤标题（简洁，5-15个字）
4. description: 详细的操作说明（描述具体如何操作，30-100个字）
5. confidence: 你对这个步骤识别的自信度（0.0-1.0），评判标准：
   - 1.0: 字幕明确描述了具体操作，非常确定
   - 0.7-0.9: 字幕大致能推断操作，但细节不够清晰
   - 0.4-0.6: 字幕模糊，需要看画面才能确认具体操作
   - 0.0-0.3: 几乎无法从字幕判断，纯靠猜测

请按照以下JSON格式输出：
[
    {
        "step": 1,
        "time": "00:15",
        "title": "打开设置页面",
        "description": "点击屏幕左上角的菜单图标，在弹出的侧边栏中选择「设置」选项，进入系统设置页面。",
        "confidence": 0.9
    }
]

注意：
- 步骤数量没有限制，有多少步就输出多少步，不要人为合并或凑数，完全根据字幕内容如实拆分,当视频长度越长时拆分的越多，最多次数为10次，最少次数为1次。
- 时间格式必须为 "MM:SS"
- 根据字幕语义判断步骤的起止范围，time 取该步骤中最关键操作的时间点
- description 要具体、可操作，结合字幕内容让读者能照着做
- confidence 要诚实评估，不确定的地方就给低分
- 只输出JSON，不要添加其他文字"""

        user_prompt = f"""以下是操作视频的字幕内容：

{subtitle_text}

请分析字幕，识别出所有操作步骤。"""

        print("正在通过字幕分析识别操作步骤...")

        result = await self._chat_completion_text(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        steps = self._parse_json_response(result)

        return steps

    # ========== 视频分析：识别操作步骤（可选增强模式，上传视频，较贵） ==========

    async def analyze_video(
        self, video_path: str, fps: float = 1.0, file_id: str = None
    ) -> List[Dict]:
        """
        分析视频，识别操作步骤
        :param video_path: 视频文件路径
        :param fps: 抽帧频率，默认1帧/秒
        :param file_id: 已上传的文件ID（可选，跳过上传）
        :return: 操作步骤列表
        """
        system_prompt = """你是一个专业的操作视频分析助手。请仔细观看上传的视频，识别出视频中展示的所有操作步骤。

对于每个步骤，请提供：
1. step: 步骤编号（从1开始）
2. time: 该步骤画面最具代表性的时间点（用于截图）
3. title: 步骤标题（简洁，5-15个字）
4. description: 详细的操作说明（描述具体如何操作，30-100个字）

请按照以下JSON格式输出：
[
    {
        "step": 1,
        "time": "00:15",
        "title": "打开设置页面",
        "description": "点击屏幕左上角的菜单图标，在弹出的侧边栏中选择「设置」选项，进入系统设置页面。"
    },
    {
        "step": 2,
        "time": "00:42",
        "title": "修改用户名",
        "description": "在设置页面中找到「个人信息」区域，点击用户名右侧的编辑按钮，输入新的用户名后点击保存。"
    }
]

注意：
- 时间格式必须为 "MM:SS"
- 选择每个步骤中最能展示操作内容的画面时间点
- description 要具体、可操作，让读者能照着做
- 只输出JSON，不要添加其他文字"""

        try:
            if not self.llm_client.supports(Capability.VIDEO_UNDERSTANDING):
                raise ProviderFeatureUnsupportedError(
                    provider=self.llm_client.provider,
                    capability=Capability.VIDEO_UNDERSTANDING,
                    hint="请切换到支持视频理解的平台（如火山 Ark）或改用字幕分析模式。",
                )

            if not file_id:
                if not self.llm_client.supports(Capability.FILE_UPLOAD):
                    raise ProviderFeatureUnsupportedError(
                        provider=self.llm_client.provider,
                        capability=Capability.FILE_UPLOAD,
                        hint="当前平台不支持视频文件上传，请切换平台或使用字幕分析模式。",
                    )
                print(f"正在上传视频: {video_path}")
                file_id = await self.llm_client.upload_video_file(video_path, fps=fps)
                print(f"视频上传成功，File ID: {file_id}")
            else:
                print(f"使用已上传的文件: {file_id}")

            print("正在分析视频，识别操作步骤...")
            result = await self.llm_client.analyze_video(
                file_id=file_id,
                system_prompt=system_prompt,
                user_text="请分析这个操作视频，识别出所有操作步骤",
            )
            steps = self._parse_json_response(result)

            return steps

        except ProviderFeatureUnsupportedError:
            # Let the caller decide how to degrade (usually: fall back to
            # subtitle-based analysis). Re-raise so upper layers can surface
            # a precise error code to the frontend.
            raise
        except Exception as e:
            print(f"分析视频时出错: {e}")
            return []

    # ========== 截图生成 ==========

    def generate_screenshot(
        self, video_path: Path, output_dir: Path, timestamp: int, step_num: int = None
    ) -> Optional[Path]:
        """
        使用 ffmpeg-python 生成截图
        :param step_num: 步骤编号，如果提供则使用 step_XX 命名
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        if step_num is not None:
            filename = f"step_{step_num:02d}.jpg"
        else:
            mm = timestamp // 60
            ss = timestamp % 60
            filename = f"screenshot_{mm:02d}_{ss:02d}.jpg"

        output_path = output_dir / filename

        logging.info("生成截图：step=%s, time=%ss, file=%s", step_num, timestamp, output_path)
        if ffmpeg is None:
            logging.warning("ffmpeg-python 未安装，回退到命令行 ffmpeg。")
            cmd = [
                self.ffmpeg_cmd,
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(output_path),
                "-y",
            ]
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                logging.warning(
                    "截图失败：step=%s, time=%ss, rc=%s, stderr=%s",
                    step_num,
                    timestamp,
                    result.returncode,
                    (result.stderr or "").strip()[-240:],
                )
                return None
        else:
            try:
                (
                    ffmpeg.input(str(video_path), ss=max(0, int(timestamp)))
                    .output(str(output_path), vframes=1, **{"q:v": 2})
                    .overwrite_output()
                    .run(
                        cmd=self.ffmpeg_cmd,
                        capture_stdout=True,
                        capture_stderr=True,
                        quiet=True,
                    )
                )
            except ffmpeg.Error as exc:
                stderr_text = ""
                if exc.stderr:
                    stderr_text = exc.stderr.decode("utf-8", errors="ignore").strip()[-240:]
                logging.warning(
                    "截图失败：step=%s, time=%ss, stderr=%s",
                    step_num,
                    timestamp,
                    stderr_text,
                )
                return None
            except Exception as exc:
                logging.warning("截图异常：step=%s, time=%ss, err=%s", step_num, timestamp, exc)
                return None

        if not output_path.exists():
            logging.warning("截图失败：step=%s, time=%ss, 输出文件不存在", step_num, timestamp)
            return None
        return output_path

    def generate_screenshots_from_steps(
        self,
        video_path: str,
        steps: List[Dict],
        output_dir: str = "images",
        max_workers: Optional[int] = None,
    ) -> List[Path]:
        """
        根据步骤列表批量生成截图
        :return: 截图文件路径列表
        """
        video_path = Path(video_path)
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        screenshot_tasks = []
        for idx, step in enumerate(steps, start=1):
            time_str = step.get("time")
            if not time_str:
                logging.warning(f"步骤缺少 'time' 字段，跳过: {step}")
                continue

            try:
                timestamp = self._parse_timestamp(str(time_str))
            except (TypeError, ValueError) as e:
                logging.warning(f"时间格式错误 {time_str}: {e}，跳过")
                continue

            try:
                step_num = int(step.get("step", idx))
            except (TypeError, ValueError):
                step_num = idx
            screenshot_tasks.append((step_num, timestamp))

        if not screenshot_tasks:
            return []

        if max_workers is None:
            raw_screenshot_workers = str(os.getenv("SCREENSHOT_MAX_WORKERS", "")).strip()
            default_screenshot_workers = 2
            if raw_screenshot_workers:
                try:
                    parsed_workers = int(raw_screenshot_workers)
                except (TypeError, ValueError):
                    parsed_workers = default_screenshot_workers
            else:
                parsed_workers = default_screenshot_workers
            max_workers = max(1, min(parsed_workers, os.cpu_count() or 2))
        max_workers = max(1, min(max_workers, len(screenshot_tasks)))

        screenshot_paths: List[Path] = []
        if max_workers == 1:
            for step_num, timestamp in screenshot_tasks:
                screenshot_path = self.generate_screenshot(
                    video_path, output_dir_path, timestamp, step_num=step_num
                )
                if screenshot_path:
                    screenshot_paths.append(screenshot_path)
                    print(f"已生成截图: {screenshot_path}")
            return screenshot_paths

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    self.generate_screenshot,
                    video_path,
                    output_dir_path,
                    timestamp,
                    step_num,
                ): step_num
                for step_num, timestamp in screenshot_tasks
            }

            for future in as_completed(future_map):
                step_num = future_map[future]
                screenshot_path = future.result()
                if screenshot_path:
                    screenshot_paths.append(screenshot_path)
                    print(f"已生成截图: {screenshot_path}")
                else:
                    logging.warning("步骤 %s 截图生成失败", step_num)

        screenshot_paths.sort(key=lambda p: p.name)

        return screenshot_paths

    # ========== AI 看图增强（低自信度步骤） ==========

    async def enhance_steps_with_vision(
        self,
        steps: List[Dict],
        image_dir: str,
        srt_path: str = None,
        max_calls: int = 10,
    ) -> List[Dict]:
        """
        对低自信度的步骤，调用 AI 看截图来增强描述
        :param steps: 步骤列表（含 confidence）
        :param image_dir: 截图目录
        :param srt_path: SRT字幕文件（可选，提供对应时间段的字幕给 AI 参考）
        :param max_calls: 最多调用 AI 看图的次数
        :return: 增强后的步骤列表
        """
        # 按 confidence 排序，取最低的 max_calls 个
        steps_with_idx = [(i, step) for i, step in enumerate(steps)]
        steps_with_idx.sort(key=lambda x: x[1].get("confidence", 1.0))
        to_enhance = steps_with_idx[:max_calls]

        # 解析字幕备用
        subtitles = []
        if srt_path and os.path.exists(srt_path):
            subtitles = self.parse_srt(srt_path)

        raw_concurrency = str(os.getenv("VISION_MAX_CONCURRENCY", "")).strip()
        try:
            vision_concurrency = int(raw_concurrency) if raw_concurrency else 4
        except (TypeError, ValueError):
            vision_concurrency = 4
        vision_concurrency = max(1, min(vision_concurrency, 8))
        vision_semaphore = asyncio.Semaphore(vision_concurrency)

        print(
            f"将对 {len(to_enhance)} 个低自信度步骤进行 AI 看图增强"
            f"（最多 {max_calls} 次，并发 {vision_concurrency}）"
        )

        async def _enhance_one(idx, step):
            step_num = step.get("step", idx + 1)
            confidence = step.get("confidence", 0)
            img_path = Path(image_dir) / f"step_{step_num:02d}.jpg"

            if not img_path.exists():
                print(f"  步骤{step_num}: 截图不存在，跳过")
                return None

            if not step.get("title") or not step.get("description"):
                print(f"  步骤{step_num}: 缺少 title 或 description，跳过")
                return None

            # 读取图片转 base64
            with open(img_path, "rb") as f:
                img_base64 = base64.b64encode(f.read()).decode("utf-8")
            img_data_url = f"data:image/jpeg;base64,{img_base64}"

            # 提取该步骤时间段内的字幕
            step_subtitle = ""
            if subtitles:
                time_str = step.get("time", "00:00")
                try:
                    step_seconds = self._parse_timestamp(str(time_str))
                except (TypeError, ValueError):
                    step_seconds = 0
                nearby = [
                    s for s in subtitles if abs(s["start_seconds"] - step_seconds) < 30
                ]
                if nearby:
                    step_subtitle = "\n".join(
                        [f"[{s['start_time']}] {s['text']}" for s in nearby]
                    )

            user_content = [
                {
                    "type": "text",
                    "text": f"这是操作视频第{step_num}步的截图。\n\n当前字幕分析结果：\n- 标题：{step.get('title', '未知')}\n- 描述：{step.get('description', '未知')}\n- 自信度：{confidence}",
                },
                {"type": "image_url", "image_url": {"url": img_data_url}},
            ]
            if step_subtitle:
                user_content.append(
                    {"type": "text", "text": f"\n该时间段附近的字幕：\n{step_subtitle}"}
                )
            user_content.append(
                {
                    "type": "text",
                    "text": '\n请根据截图画面，修正或补充这个步骤的标题和描述。只输出JSON，格式：{"title": "...", "description": "..."}',
                }
            )

            print(f"  步骤{step_num} (confidence={confidence:.1f}): AI 看图分析中...")

            async with vision_semaphore:
                result = await self._chat_completion_text(
                    [
                        {
                            "role": "system",
                            "content": '你是专业的视频步骤纠错助手。请结合截图与上下文信息，修正当前步骤的标题和描述。仅输出 JSON 对象，格式必须为 {"title":"...","description":"..."}，不要输出任何额外文本。',
                        },
                        {"role": "user", "content": user_content},
                    ]
                )
            enhanced = self._parse_json_object_response(result)
            return idx, enhanced

        enhance_results = await asyncio.gather(
            *(_enhance_one(idx, step) for idx, step in to_enhance),
            return_exceptions=True,
        )
        for item in enhance_results:
            if isinstance(item, Exception):
                print(f"    解析增强结果失败: {item}，保留原始结果")
                continue
            if not item:
                continue
            idx, enhanced = item
            if not isinstance(enhanced, dict):
                continue
            old_title = steps[idx]["title"]
            steps[idx]["title"] = enhanced.get("title", steps[idx]["title"])
            steps[idx]["description"] = enhanced.get(
                "description", steps[idx]["description"]
            )
            steps[idx]["enhanced"] = True
            print(f"    ✓ 已增强: 「{old_title}」→「{steps[idx]['title']}」")

        return steps

    # ========== 步骤操作文档生成 ==========

    @staticmethod
    def _normalize_compare_text(value: Any) -> str:
        """Normalize text for loose inclusion checks."""
        if value is None:
            return ""
        text = str(value).strip().lower()
        return re.sub(r"\s+", "", text)

    def _is_markdown_aligned_with_steps(
        self, markdown_content: str, steps: List[Dict]
    ) -> bool:
        """Check whether generated markdown reflects edited step titles and descriptions."""
        normalized_doc = self._normalize_compare_text(markdown_content)
        if not normalized_doc:
            return False

        for idx, step in enumerate(steps, start=1):
            title = str(step.get("title", "") or "").strip()
            description = str(step.get("description", "") or "").strip()

            if title:
                title_anchor = self._normalize_compare_text(title)
                if title_anchor and title_anchor not in normalized_doc:
                    return False

            if description:
                description_anchor = self._normalize_compare_text(description)
                if len(description_anchor) > 32:
                    description_anchor = description_anchor[:32]
                if description_anchor and description_anchor not in normalized_doc:
                    return False

            step_no = step.get("step", idx)
            zh_heading_anchor = self._normalize_compare_text(f"步骤{step_no}")
            en_heading_anchor = self._normalize_compare_text(f"step{step_no}")
            if (
                zh_heading_anchor not in normalized_doc
                and en_heading_anchor not in normalized_doc
            ):
                return False

        return True

    def _build_document_from_steps(self, steps: List[Dict], image_dir: str = "images") -> str:
        """Build a deterministic document from user-edited steps as a strict fallback."""
        # 用最后一步的时间戳粗略估算预计耗时（不可解析时省略）。
        estimated = ""
        for step in reversed(steps):
            raw_time = str(step.get("time", "") or "").strip()
            if not raw_time:
                continue
            try:
                total_seconds = self._parse_timestamp(raw_time)
            except (TypeError, ValueError):
                continue
            minutes = max(1, round(total_seconds / 60))
            estimated = f"约 {minutes} 分钟（按视频时长估算，实际操作可能更久）"
            break

        lines: List[str] = [
            "# 操作步骤总结",
            "",
            "## 概述",
            f"- **适用人群**：需要按视频完成本套操作的读者",
            "- **前置条件**：请提前准备好视频中涉及的账号、软件或权限",
            f"- **预计耗时**：{estimated or '视实际操作熟练度而定'}",
            f"- **简介**：本指南共 {len(steps)} 个步骤，按视频内容整理为可照做的操作流程。",
            "- 本文档按用户编辑后的步骤内容生成。",
            "",
        ]

        for idx, step in enumerate(steps, start=1):
            raw_step_no = step.get("step", idx)
            try:
                step_no = int(raw_step_no)
            except (TypeError, ValueError):
                step_no = idx

            title = str(step.get("title", "") or "").strip() or f"步骤 {step_no}"
            time_text = str(step.get("time", "") or "").strip()
            description = str(step.get("description", "") or "").strip() or "（未填写步骤说明）"
            screenshot_name = f"step_{step_no:02d}.jpg"

            lines.extend(
                [
                    f"## 步骤 {step_no}：{title}",
                    f"- 时间：{time_text or '00:00'}",
                    "",
                    f"![步骤{step_no}截图]({image_dir}/{screenshot_name})",
                    "",
                    "### 操作说明",
                    description,
                    "",
                ]
            )

        return "\n".join(lines).rstrip() + "\n"

    async def generate_step_document(
        self,
        steps: List[Dict],
        output_path: str = "operation_guide.md",
        srt_path: str = None,
        image_dir: str = "images",
        web_search: bool = False,
        respect_step_content: bool = False,
    ) -> str:
        """
        生成步骤操作文档（Markdown格式）
        :param steps: AI识别出的步骤列表
        :param output_path: 输出文件路径
        :param srt_path: SRT字幕文件路径（可选，用于补充文字内容）
        :param image_dir: 截图目录
        :param web_search: 是否启用联网搜索增强
        :param respect_step_content: 是否严格遵循传入步骤内容（用于用户手工编辑后重生成）
        """
        # 准备字幕信息（如果有）
        subtitle_text = ""
        if srt_path and os.path.exists(srt_path):
            subtitles = self.parse_srt(srt_path)
            subtitle_text = "\n".join(
                [f"[{sub['start_time']}] {sub['text']}" for sub in subtitles]
            )

        # 准备步骤和截图的对应关系
        steps_info = json.dumps(steps, ensure_ascii=False, indent=2)

        # 构建截图列表（发送给 AI 时使用路径占位符）
        screenshot_list = []
        for step in steps:
            step_num = step.get("step", 0)
            filename = f"step_{step_num:02d}.jpg"
            screenshot_list.append(
                f"步骤{step_num}: ![步骤{step_num}截图]({image_dir}/{filename})"
            )

        if web_search:
            system_prompt = """你是一个专业的技术文档编写专家。请根据提供的操作步骤信息、截图和字幕内容，生成一份清晰、专业的步骤操作文档。

你拥有联网搜索能力，请主动搜索以下内容来丰富文档：
- 视频中涉及的软件/平台/工具的官方介绍和功能说明
- 相关的最佳实践、使用技巧或注意事项
- 专业术语的准确解释

要求：
1. 使用 Markdown 格式
2. 每个步骤包含：标题（## 步骤 X：标题）、截图、详细操作说明
3. 操作说明要具体、准确，让读者能照着操作
4. 结合联网搜索到的信息，补充更丰富的上下文（如软件介绍、功能说明、注意事项等）
5. 如果有字幕内容，结合字幕让描述更加准确和详细
6. 在文档开头添加结构化的「## 概述」章节，必须包含以下要点（用无序列表呈现，可结合搜索到的产品介绍）：
   - **适用人群**：这份指南适合哪些读者
   - **前置条件**：开始操作前需要准备的账号/软件/权限等
   - **预计耗时**：完成全部步骤大约需要多长时间
   - **简介**：一句话说明本指南能帮读者完成什么
7. 保持语言简洁专业
8. 在文档末尾添加「## 参考资料」章节，列出所有搜索引用的信息来源（标题+链接）
9. 直接返回 Markdown 内容，不要添加其他说明"""
        else:
            system_prompt = """你是一个专业的技术文档编写专家。请根据提供的操作步骤信息、截图和字幕内容，生成一份清晰、专业的步骤操作文档。

要求：
1. 使用 Markdown 格式
2. 每个步骤包含：标题（## 步骤 X：标题）、截图、详细操作说明
3. 操作说明要具体、准确，让读者能照着操作
4. 如果有字幕内容，结合字幕让描述更加准确和详细
5. 在文档开头添加结构化的「## 概述」章节，必须包含以下要点（用无序列表呈现）：
   - **适用人群**：这份指南适合哪些读者
   - **前置条件**：开始操作前需要准备的账号/软件/权限等
   - **预计耗时**：完成全部步骤大约需要多长时间
   - **简介**：一句话说明本指南能帮读者完成什么
6. 保持语言简洁专业
7. 直接返回 Markdown 内容，不要添加其他说明"""

        if respect_step_content:
            system_prompt += """

Additional strict requirements:
1. The provided `steps` are user-edited final content and are authoritative.
2. Keep each step title exactly aligned with the provided `title`.
3. Keep each step description semantically aligned with the provided `description`; do not override user intent.
4. Do not add/remove critical actions that conflict with the provided descriptions.
5. In each step section, keep the user-provided description text visible before any expansion.
"""

        user_prompt = f"""操作步骤信息：
{steps_info}

截图对应关系：
{chr(10).join(screenshot_list)}
"""
        if respect_step_content:
            user_prompt += """

IMPORTANT:
- These steps were manually edited by the user.
- Treat the provided title/description as the primary source of truth for each step.
- Keep each provided description text visible in the final markdown content.
"""
        if subtitle_text:
            user_prompt += f"""
视频字幕内容（供参考）：
{subtitle_text}
"""
        if web_search:
            user_prompt += "\n请先联网搜索相关信息，然后生成完整的步骤操作文档。"
        else:
            user_prompt += "\n请生成完整的步骤操作文档。"

        if web_search:
            if not self.llm_client.supports(Capability.WEB_SEARCH_TOOL):
                logging.warning(
                    "[generate_step_document] provider %s does not support web_search tool; "
                    "falling back to plain chat completion.",
                    self.llm_client.provider,
                )
                web_search = False
            else:
                print("正在调用 AI 生成步骤操作文档（联网搜索增强）...")
                try:
                    markdown_content = await self.llm_client.responses_with_tools(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        tools=[{"type": "web_search"}],
                    )
                except ProviderFeatureUnsupportedError:
                    logging.warning(
                        "[generate_step_document] provider rejected web_search capability "
                        "at runtime; falling back to plain chat completion."
                    )
                    web_search = False

        if not web_search:
            print("正在调用 AI 生成步骤操作文档...")

            markdown_content = await self._chat_completion_text(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )

        if respect_step_content and not self._is_markdown_aligned_with_steps(
            markdown_content, steps
        ):
            logging.warning(
                "Model output did not fully reflect edited steps; using strict fallback document builder."
            )
            markdown_content = self._build_document_from_steps(
                steps=steps, image_dir=image_dir
            )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        print(f"步骤操作文档已保存到: {output_path}")
        return output_path

    # ========== PDF 生成 ==========

    def generate_pdf(self, md_path: str, pdf_path: str = None) -> str:
        """
        将 Markdown 文档转换为 PDF。

        优先使用 Playwright（Chromium 无头浏览器）渲染：完整保留表格、代码块、
        嵌套列表、链接样式与中文排版。Chromium 不可用时自动回退到 FPDF 逐行渲染，
        保证任何环境下都能出 PDF。

        可用 PDF_RENDER_ENGINE=fpdf 强制走旧引擎；默认 auto（优先 Playwright）。
        :param md_path: Markdown 文件路径
        :param pdf_path: PDF 输出路径（默认同名 .pdf）
        :return: PDF 文件路径
        """
        if not pdf_path:
            pdf_path = str(Path(md_path).with_suffix(".pdf"))

        engine = str(os.getenv("PDF_RENDER_ENGINE", "auto")).strip().lower()
        if engine != "fpdf":
            try:
                from services import pdf_render

                if pdf_render.render_markdown_to_pdf(md_path, pdf_path):
                    print(f"PDF 文档已生成 (Chromium): {pdf_path}")
                    return pdf_path
                logging.info("Playwright 渲染不可用，回退 FPDF 引擎。")
            except Exception as exc:
                logging.warning("Playwright 渲染异常，回退 FPDF: %s", str(exc)[:200])

        return self._generate_pdf_fpdf(md_path, pdf_path)

    def _generate_pdf_fpdf(self, md_path: str, pdf_path: str = None) -> str:
        """
        将 Markdown 文档转换为 PDF（FPDF 逐行渲染，图片嵌入）。
        作为 Playwright 渲染不可用时的兜底实现。
        :param md_path: Markdown 文件路径
        :param pdf_path: PDF 输出路径（默认同名 .pdf）
        :return: PDF 文件路径
        """
        import markdown
        from fpdf import FPDF, XPos, YPos
        from PIL import Image

        if not pdf_path:
            pdf_path = str(Path(md_path).with_suffix(".pdf"))

        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        html_body = markdown.markdown(md_content, extensions=["tables", "fenced_code"])

        font_paths = self.FONT_PATHS
        chinese_font_added = False
        font_family = "helvetica"

        for fp in font_paths:
            if Path(fp).exists():
                font_family = "Chinese"
                break

        class PDF(FPDF):
            def header(self):
                # 仅第一页保留 "Video Analysis" 标题，其余页面不重复标题，
                # 内容直接从顶部边距开始，避免每页顶部留出大段空白。
                if self.page_no() != 1:
                    return
                self.set_font(font_family, "B", 15)
                self.cell(0, 10, "Video Analysis", border=False, align="C",
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                self.ln(4)

        pdf = PDF()

        for fp in font_paths:
            if Path(fp).exists():
                try:
                    pdf.add_font("Chinese", "", fp)
                    pdf.add_font("Chinese", "B", fp)
                    chinese_font_added = True
                    break
                except Exception:
                    continue

        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        import re
        from html import unescape

        def parse_html_to_pdf(html_text: str):
            temp_text = re.sub(
                r"<h1[^>]*>(.*?)</h1>", r"\n=== \1 ===\n", html_text, flags=re.DOTALL
            )
            temp_text = re.sub(
                r"<h2[^>]*>(.*?)</h2>", r"\n== \1 ==\n", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(
                r"<h3[^>]*>(.*?)</h3>", r"\n= \1 =\n", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(
                r"<p[^>]*>(.*?)</p>", r"\1\n", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(r"<br\s*/?>", r"\n", temp_text, flags=re.IGNORECASE)
            temp_text = re.sub(
                r"<strong[^>]*>(.*?)</strong>", r"**\1**", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(
                r"<b[^>]*>(.*?)</b>", r"**\1**", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(
                r"<em[^>]*>(.*?)</em>", r"*\1*", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(
                r"<i[^>]*>(.*?)</i>", r"*\1*", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(
                r"<code[^>]*>(.*?)</code>", r"`\1`", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(
                r"<pre[^>]*>(.*?)</pre>", r"```\n\1\n```", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(r"<table[^>]*>", r"", temp_text, flags=re.DOTALL)
            temp_text = re.sub(r"</table>", r"", temp_text)
            temp_text = re.sub(r"<tr>", r"", temp_text)
            temp_text = re.sub(r"</tr>", r"\n", temp_text)
            temp_text = re.sub(
                r"<td[^>]*>(.*?)</td>", r"\1 | ", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(
                r"<th[^>]*>(.*?)</th>", r"**\1** | ", temp_text, flags=re.DOTALL
            )
            temp_text = re.sub(r"<thead[^>]*>", r"", temp_text, flags=re.DOTALL)
            temp_text = re.sub(r"</thead>", r"", temp_text)
            temp_text = re.sub(r"<tbody[^>]*>", r"", temp_text, flags=re.DOTALL)
            temp_text = re.sub(r"</tbody>", r"", temp_text)
            temp_text = re.sub(
                r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
                r"[Image: \1]",
                temp_text,
                flags=re.DOTALL,
            )
            temp_text = re.sub(r"<[^>]+>", r"", temp_text)
            temp_text = unescape(temp_text)
            temp_text = re.sub(r"\n{3,}", r"\n\n", temp_text)
            return temp_text.strip()

        text = parse_html_to_pdf(html_body)
        base_dir = Path(md_path).parent

        current_font = "Chinese" if chinese_font_added else "helvetica"

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                pdf.ln(5)
                continue

            if line.startswith("==="):
                title = line.strip("= ").strip()
                pdf.set_font(current_font, "B", 16)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(
                    0, 10, title, border=False, new_x=XPos.LMARGIN, new_y=YPos.NEXT
                )
                pdf.ln(5)
            elif line.startswith("=="):
                title = line.strip("= ").strip()
                # 每个步骤标题前另起一页，保证“步骤标题 + 截图 + 操作说明”
                # 始终落在同一页，而不是截图与说明被拆到相邻两页。
                if pdf.get_y() > pdf.t_margin + 1:
                    pdf.add_page()
                pdf.set_font(current_font, "B", 14)
                pdf.set_text_color(44, 62, 80)
                pdf.cell(0, 8, title, border=False, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(3)
            elif line.startswith("="):
                title = line.strip("= ").strip()
                pdf.set_font(current_font, "B", 12)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(0, 7, title, border=False, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(2)
            elif line.startswith("[Image:"):
                img_match = re.search(r"\[Image: ([^\]]+)\]", line)
                if img_match:
                    img_path = img_match.group(1).strip()
                    img_full_path = base_dir / img_path
                    if img_full_path.exists():
                        try:
                            # 同时按可用宽度与最大高度约束尺寸：竖屏手机截图
                            # 很高，若只限宽会撑满整页把操作说明挤到下一页。
                            # 这里限制图片高度，并水平居中，让标题/图/说明同页。
                            epw = pdf.w - pdf.l_margin - pdf.r_margin
                            max_w = min(epw, 90.0)
                            max_h = 150.0
                            with Image.open(img_full_path) as im:
                                iw, ih = im.size
                            ratio = (iw / ih) if ih else 1.0
                            draw_w = max_w
                            draw_h = draw_w / ratio if ratio else max_h
                            if draw_h > max_h:
                                draw_h = max_h
                                draw_w = draw_h * ratio
                            x = pdf.l_margin + (epw - draw_w) / 2.0
                            pdf.image(str(img_full_path), x=x, w=draw_w, h=draw_h)
                            pdf.ln(3)
                        except Exception:
                            pdf.cell(
                                0,
                                7,
                                f"[图片: {img_path}]",
                                border=False,
                                new_x=XPos.LMARGIN,
                                new_y=YPos.NEXT,
                            )
                    else:
                        pdf.cell(
                            0,
                            7,
                            f"[图片: {img_path}]",
                            border=False,
                            new_x=XPos.LMARGIN,
                            new_y=YPos.NEXT,
                        )
            else:
                pdf.set_font(current_font, "", 10)
                pdf.set_text_color(51, 51, 51)
                pdf.multi_cell(0, 5, line)
                pdf.ln(2)

        pdf.output(pdf_path)

        print(f"PDF 文档已生成: {pdf_path}")
        return pdf_path

    # ========== 工具方法 ==========

    def save_results(self, results: List[Dict], output_path: str):
        """将分析结果保存到JSON文件"""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"分析结果已保存到: {output_path}")

    def parse_srt(self, srt_path):
        """解析srt文件，返回字幕列表"""
        srt_file = Path(srt_path).resolve(strict=False)
        try:
            stat_info = srt_file.stat()
            cache_key = (
                str(srt_file),
                int(stat_info.st_size),
                int(getattr(stat_info, "st_mtime_ns", int(stat_info.st_mtime * 1e9))),
            )
            if self._parsed_srt_cache_key == cache_key and self._parsed_srt_cache_value is not None:
                return list(self._parsed_srt_cache_value)
        except OSError:
            cache_key = None

        with open(srt_file, "r", encoding="utf-8") as f:
            content = f.read()

        content = content.replace("\r\n", "\n").replace("\r", "\n")
        subtitle_blocks = re.split(r"\n{2,}", content.strip())
        subtitles = []

        for block in subtitle_blocks:
            lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
            if len(lines) >= 3:
                try:
                    index = int(lines[0])
                    time_range = lines[1].strip()
                    text = " ".join(lines[2:])
                    start_time, end_time = [
                        item.strip() for item in time_range.split(" --> ", 1)
                    ]
                    start_seconds = self.time_to_seconds(start_time)
                    subtitles.append(
                        {
                            "index": index,
                            "start_time": start_time,
                            "end_time": end_time,
                            "start_seconds": start_seconds,
                            "text": text,
                        }
                    )
                except Exception:
                    continue

        if cache_key is not None:
            self._parsed_srt_cache_key = cache_key
            self._parsed_srt_cache_value = list(subtitles)
        return subtitles

    def time_to_seconds(self, time_str):
        """将SRT时间字符串转换为秒数"""
        time_str = time_str.strip().replace(".", ",")
        h, m, s = time_str.split(":")
        if "," in s:
            s, ms = s.split(",", 1)
        else:
            ms = "0"
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
