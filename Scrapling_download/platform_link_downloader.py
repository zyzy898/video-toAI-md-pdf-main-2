from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Callable, Dict, Tuple
from urllib.parse import parse_qs, urlparse

try:
    from Scrapling_download.shared_llm_config import get_shared_llm_config
except Exception:
    from shared_llm_config import get_shared_llm_config


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


class PlatformLinkDownloader:
    def __init__(self, logger_obj: Any | None = None, *, use_llm: bool = True) -> None:
        self.logger = logger_obj
        self.use_llm = bool(use_llm)

    def detect_platform(self, raw_url: str) -> str:
        host = str(urlparse(str(raw_url or "").strip()).netloc or "").lower()
        if any(token in host for token in ("bilibili.com", "b23.tv")):
            return "bilibili"
        if any(token in host for token in ("douyin.com", "iesdouyin.com", "v.douyin.com")):
            return "douyin"
        if any(token in host for token in ("xiaohongshu.com", "xhslink.com")):
            return "xiaohongshu"
        return ""

    def maybe_download(
        self,
        raw_url: str,
        target_path: Path,
        *,
        max_bytes: int,
    ) -> Tuple[Path, Dict[str, Any]] | None:
        platform = self.detect_platform(raw_url)
        if not platform:
            return None

        normalized_url = self._normalize_platform_url(platform, raw_url)
        requested_path = self._normalize_output_path(target_path)
        before = self._snapshot_candidates(requested_path)

        try:
            success = self._run_platform_downloader(
                platform=platform,
                source_url=normalized_url,
                output_path=requested_path,
            )
            if not success:
                raise RuntimeError(f"{platform} downloader returned failure")

            final_path = self._resolve_downloaded_file(requested_path, before)
            if final_path is None or not final_path.exists():
                raise RuntimeError("downloader returned success but no output file was found")

            file_size = final_path.stat().st_size if final_path.exists() else 0
            if file_size <= 0:
                self._safe_remove_file(final_path)
                raise RuntimeError("download result is empty")
            if file_size > int(max_bytes):
                self._safe_remove_file(final_path)
                raise ValueError(
                    f"remote file exceeds size limit (>{int(max_bytes) / (1024 * 1024):.1f}MB)"
                )

            video_id = self._extract_platform_media_id(platform, normalized_url)
            meta = {
                "download_source": f"platform_{platform}_downloader_llm",
                "resolved_source_url": normalized_url,
                "title": "",
                "video_id": video_id,
                "candidate_batch": "platform_llm_downloader",
                "bytes": file_size,
                "platform": platform,
            }
            return final_path, meta
        except Exception:
            self._cleanup_candidates(requested_path, before)
            raise

    def _run_platform_downloader(
        self,
        *,
        platform: str,
        source_url: str,
        output_path: Path,
    ) -> bool:
        output_str = str(output_path)
        if platform == "bilibili":
            import Scrapling_download.bilibili_downloader_llm

            self._apply_env_model_to_module(Scrapling_download.bilibili_downloader_llm)
            downloader = Scrapling_download.bilibili_downloader_llm.BilibiliDownloader(use_llm=self.use_llm)
            return bool(downloader.download(source_url, output_str))

        if platform == "xiaohongshu":
            import Scrapling_download.xiaohongshu_downloader_llm

            self._apply_env_model_to_module(Scrapling_download.xiaohongshu_downloader_llm)
            downloader = Scrapling_download.xiaohongshu_downloader_llm.XiaoHongShuDownloader(use_llm=self.use_llm)
            return bool(downloader.download(source_url, output_str))

        if platform == "douyin":
            import Scrapling_download.douyin_downloader_llm

            self._apply_env_model_to_module(Scrapling_download.douyin_downloader_llm)
            downloader = Scrapling_download.douyin_downloader_llm.DouyinDownloader(use_llm=self.use_llm)
            return bool(self._run_async_callable(lambda: downloader.download(source_url, output_str)))

        raise ValueError(f"unsupported platform: {platform}")

    def _run_async_callable(self, coro_factory: Callable[[], Any]) -> Any:
        try:
            return asyncio.run(coro_factory())
        except RuntimeError as exc:
            if "cannot be called from a running event loop" not in str(exc):
                raise
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro_factory())
            finally:
                loop.close()

    def _normalize_platform_url(self, platform: str, raw_url: str) -> str:
        url_text = str(raw_url or "").strip()
        if platform != "douyin":
            return url_text

        parsed = urlparse(url_text)
        media_id = self._extract_douyin_media_id(url_text)
        if media_id:
            return f"https://www.douyin.com/video/{media_id}"

        query = parse_qs(parsed.query, keep_blank_values=False)
        for key in ("modal_id", "aweme_id", "video_id", "item_id"):
            values = query.get(key, [])
            if not values:
                continue
            candidate = re.sub(r"\D", "", str(values[0] or ""))
            if len(candidate) >= 8:
                return f"https://www.douyin.com/video/{candidate}"

        return url_text

    def _extract_douyin_media_id(self, text: str) -> str:
        patterns = (
            r"/video/(\d{8,25})",
            r"/share/video/(\d{8,25})",
            r"(?:modal_id|aweme_id|video_id|item_id)=(\d{8,25})",
        )
        source = str(text or "")
        for pattern in patterns:
            match = re.search(pattern, source)
            if match:
                return str(match.group(1) or "").strip()
        return ""

    def _extract_platform_media_id(self, platform: str, url_text: str) -> str:
        value = str(url_text or "")
        if platform == "douyin":
            return self._extract_douyin_media_id(value)
        if platform == "bilibili":
            match = re.search(r"/video/(BV[\w]+)", value)
            if match:
                return str(match.group(1) or "").strip()
        if platform == "xiaohongshu":
            match = re.search(r"/explore/([a-zA-Z0-9]+)", value)
            if match:
                return str(match.group(1) or "").strip()
        return ""

    def _normalize_output_path(self, target_path: Path) -> Path:
        output_path = Path(target_path)
        if output_path.suffix.lower() != ".mp4":
            output_path = output_path.with_suffix(".mp4")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    def _snapshot_candidates(self, requested_path: Path) -> set[str]:
        parent = requested_path.parent
        stem = requested_path.stem
        snapshot: set[str] = set()
        if not parent.exists():
            return snapshot
        for path_obj in parent.glob(f"{stem}*"):
            if path_obj.is_file() and path_obj.suffix.lower() in VIDEO_SUFFIXES:
                snapshot.add(str(path_obj.resolve()))
        return snapshot

    def _resolve_downloaded_file(
        self,
        requested_path: Path,
        before: set[str],
    ) -> Path | None:
        direct = requested_path
        if direct.exists() and direct.is_file() and str(direct.resolve()) not in before:
            return direct

        candidates: list[Path] = []
        parent = requested_path.parent
        stem = requested_path.stem
        for path_obj in parent.glob(f"{stem}*"):
            if not path_obj.is_file() or path_obj.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            resolved = str(path_obj.resolve())
            if resolved in before:
                continue
            candidates.append(path_obj)

        if not candidates:
            if direct.exists() and direct.is_file():
                return direct
            return None
        candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return candidates[0]

    def _cleanup_candidates(self, requested_path: Path, before: set[str]) -> None:
        parent = requested_path.parent
        stem = requested_path.stem
        if not parent.exists():
            return
        for path_obj in parent.glob(f"{stem}*"):
            if not path_obj.is_file() or path_obj.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            resolved = str(path_obj.resolve())
            if resolved in before:
                continue
            self._safe_remove_file(path_obj)

    def _safe_remove_file(self, file_path: Path) -> None:
        path_obj = Path(file_path)
        try:
            if path_obj.exists():
                path_obj.unlink()
        except Exception as exc:
            self._log_info("cleanup temp file failed (%s): %s", path_obj, exc)

    def _apply_env_model_to_module(self, module_obj: Any) -> None:
        api_key, base_url, model_name = get_shared_llm_config()
        setattr(module_obj, "LLM_API_KEY", str(api_key or "").strip())
        setattr(module_obj, "LLM_BASE_URL", str(base_url or "").strip())
        setattr(module_obj, "LLM_MODEL", str(model_name or "").strip())

    def _log_info(self, message: str, *args: Any) -> None:
        if self.logger is None:
            return
        try:
            self.logger.info(message, *args)
        except Exception:
            pass
