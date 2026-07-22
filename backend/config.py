from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _first_env(*names: str) -> str | None:
    """Return the first non-empty environment variable in ``names``."""

    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


TEMPERATURE = _float_env("VIFA_TEMPERATURE", 0.7)
REQUEST_TIMEOUT_SECONDS = _float_env("VIFA_REQUEST_TIMEOUT_SECONDS", 120.0)
RETRY_BASE_DELAY_SECONDS = _float_env("VIFA_RETRY_BASE_DELAY_SECONDS", 1.0)
MAX_RETRIES = max(1, _int_env("VIFA_MAX_RETRIES", 3))

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
CHAIRMAN_MODEL = os.getenv("CHAIRMAN_MODEL", GEMINI_MODEL)
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3-pro-image")
IMAGE_API_KEY = _first_env(
    "NANO_BANANA_PRO_API_KEY",
    "GEMINI_IMAGE_API_KEY",
    "GEMINI_API_KEY",
)
IMAGE_BASE_URL = os.getenv(
    "GEMINI_IMAGE_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/models",
)
IMAGE_REQUEST_TIMEOUT_SECONDS = _float_env(
    "VIFA_IMAGE_REQUEST_TIMEOUT_SECONDS", 300.0
)
IMAGE_ASPECT_RATIO = os.getenv("VIFA_IMAGE_ASPECT_RATIO", "").strip()
IMAGE_SIZE = os.getenv("VIFA_IMAGE_SIZE", "").strip()


def _model(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str,
    max_output_tokens: int = 16_384,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": TEMPERATURE,
        "max_output_tokens": max_output_tokens,
    }


OPENAI_BASE_URL = os.getenv(
    "OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"
)
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/models"
)
ANTHROPIC_BASE_URL = os.getenv(
    "ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1/messages"
)

MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "gpt_stage1": _model(
        provider="openai",
        model=OPENAI_MODEL,
        api_key=_first_env("OPENAI_API_KEY_STAGE1", "OPENAI_API_KEY"),
        base_url=OPENAI_BASE_URL,
    ),
    "gemini_stage1": _model(
        provider="google",
        model=GEMINI_MODEL,
        api_key=_first_env("GEMINI_API_KEY_STAGE1", "GEMINI_API_KEY_S1", "GEMINI_API_KEY"),
        base_url=GEMINI_BASE_URL,
    ),
    "claude_stage1": _model(
        provider="anthropic",
        model=ANTHROPIC_MODEL,
        api_key=_first_env("ANTHROPIC_API_KEY_STAGE1", "ANTHROPIC_API_KEY"),
        base_url=ANTHROPIC_BASE_URL,
        max_output_tokens=16_384,
    ),
    "gpt_stage2": _model(
        provider="openai",
        model=OPENAI_MODEL,
        api_key=_first_env("OPENAI_API_KEY_STAGE2", "OPENAI_API_KEY"),
        base_url=OPENAI_BASE_URL,
    ),
    "gemini_stage2": _model(
        provider="google",
        model=GEMINI_MODEL,
        api_key=_first_env("GEMINI_API_KEY_STAGE2", "GEMINI_API_KEY_S2", "GEMINI_API_KEY"),
        base_url=GEMINI_BASE_URL,
    ),
    "claude_stage2": _model(
        provider="anthropic",
        model=ANTHROPIC_MODEL,
        api_key=_first_env("ANTHROPIC_API_KEY_STAGE2", "ANTHROPIC_API_KEY"),
        base_url=ANTHROPIC_BASE_URL,
        max_output_tokens=16_384,
    ),
    # A distinct registry entry keeps Chairman provenance isolated from the
    # Gemini expert, even when both use the same provider account in dev.
    "gemini_chairman": _model(
        provider="google",
        model=CHAIRMAN_MODEL,
        api_key=_first_env("CHAIRMAN_API_KEY", "GEMINI_API_KEY"),
        base_url=GEMINI_BASE_URL,
    ),
}

COUNCIL_MEMBERS_STAGE1 = ["gpt_stage1", "gemini_stage1", "claude_stage1"]
COUNCIL_MEMBERS_STAGE2 = ["gpt_stage2", "gemini_stage2", "claude_stage2"]
CHAIRMAN_ID = "gemini_chairman"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("VIFA_DATA_DIR", PROJECT_ROOT / "data" / "conversations"))
LOCAL_IMAGE_DIR = Path(
    os.getenv("VIFA_LOCAL_IMAGE_DIR", PROJECT_ROOT / "local_storage" / "images")
)
MAX_UPLOAD_BYTES = max(
    1, _int_env("VIFA_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
)

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
