from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ENV_PATH = PROJECT_ROOT / ".env"
SHARED_LLM_ENV_KEYS = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


def _read_shared_llm_values_from_env_file() -> Tuple[str, str, str]:
    if not PROJECT_ENV_PATH.exists():
        return "", "", ""
    values = dotenv_values(PROJECT_ENV_PATH)
    api_key = str(values.get("LLM_API_KEY") or "").strip()
    base_url = str(values.get("LLM_BASE_URL") or "").strip()
    model_name = str(values.get("LLM_MODEL") or "").strip()
    return api_key, base_url, model_name


def _apply_shared_llm_values_to_process_env(api_key: str, base_url: str, model_name: str) -> None:
    resolved = {
        "LLM_API_KEY": str(api_key or "").strip(),
        "LLM_BASE_URL": str(base_url or "").strip(),
        "LLM_MODEL": str(model_name or "").strip(),
    }
    for key in SHARED_LLM_ENV_KEYS:
        value = resolved.get(key, "")
        if value:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


def get_shared_llm_config() -> Tuple[str, str, str]:
    api_key, base_url, model_name = _read_shared_llm_values_from_env_file()
    _apply_shared_llm_values_to_process_env(api_key, base_url, model_name)
    return api_key, base_url, model_name
