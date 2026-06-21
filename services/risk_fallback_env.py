"""Risk visual-fallback .env template service.

Maintains the system-managed block in .env that holds the optional visual
risk-moderation fallback model credentials, and reads those options back.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple
import logging


class RiskFallbackEnvService:
    def __init__(
        self,
        env_path: Path,
        block_marker: str,
        legacy_marker: str,
        env_keys: Tuple[str, str, str],
        logger_obj: logging.Logger,
    ):
        self.env_path = env_path
        self.block_marker = block_marker
        self.legacy_marker = legacy_marker
        self.env_keys = env_keys
        self.logger = logger_obj

    def ensure_env_file(self) -> None:
        info_lines = [
            self.block_marker,
            "# 系统自动创建，请勿向普通用户暴露。",
            "# 该兜底模型必须是视觉模型（支持图片输入）。",
            "# 仅在主视觉风控模型不可用时启用。",
        ]
        expected_lines = [*info_lines, *(f"{key}=" for key in self.env_keys)]
        try:
            if not self.env_path.exists():
                self.env_path.write_text("\n".join(expected_lines) + "\n", encoding="utf-8")
                return

            raw_text = self.env_path.read_text(encoding="utf-8")
            missing_keys = [
                key
                for key in self.env_keys
                if re.search(rf"^\s*{re.escape(key)}\s*=", raw_text, re.MULTILINE) is None
            ]
            missing_marker = (
                self.block_marker not in raw_text
                and self.legacy_marker not in raw_text
            )
            if not missing_keys and not missing_marker:
                return

            append_lines: List[str] = []
            if missing_marker:
                append_lines.extend(info_lines)
            append_lines.extend(f"{key}=" for key in missing_keys)
            if not append_lines:
                return

            with open(self.env_path, "a", encoding="utf-8") as f:
                if raw_text and not raw_text.endswith(("\n", "\r")):
                    f.write("\n")
                f.write("\n".join(append_lines) + "\n")
        except (OSError, UnicodeDecodeError) as exc:
            self.logger.warning("无法自动维护 .env 风控兜底模板: %s", exc)

    def read_model_options(self) -> Tuple[str, str, str]:
        api_key = str(os.getenv("RISK_FALLBACK_API_KEY", "")).strip()
        model_name = str(os.getenv("RISK_FALLBACK_MODEL_NAME", "")).strip()
        model_base_url = str(os.getenv("RISK_FALLBACK_MODEL_BASE_URL", "")).strip()
        return api_key, model_name, model_base_url
