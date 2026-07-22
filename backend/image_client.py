from __future__ import annotations

import asyncio
import base64
import binascii
import re
import uuid
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote

import httpx

from .config import (
    IMAGE_API_KEY,
    IMAGE_ASPECT_RATIO,
    IMAGE_BASE_URL,
    IMAGE_MODEL,
    IMAGE_REQUEST_TIMEOUT_SECONDS,
    IMAGE_SIZE,
    LOCAL_IMAGE_DIR,
    MAX_RETRIES,
    RETRY_BASE_DELAY_SECONDS,
)


class ImageGenerationError(RuntimeError):
    """Raised when Nano Banana Pro cannot return a usable image."""


def _extension(mime_type: str) -> str:
    return {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime_type, ".png")


def _parts(prompt: str, references: list[tuple[bytes, str]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for data, mime_type in references:
        result.append(
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(data).decode("ascii"),
                }
            }
        )
    result.append({"text": prompt})
    return result


def _generation_config() -> dict[str, Any]:
    config: dict[str, Any] = {"responseModalities": ["IMAGE"]}
    image_config: dict[str, str] = {}
    if IMAGE_ASPECT_RATIO:
        image_config["aspectRatio"] = IMAGE_ASPECT_RATIO
    if IMAGE_SIZE:
        image_config["imageSize"] = IMAGE_SIZE
    if image_config:
        config["imageConfig"] = image_config
    return config


def _extract_image(payload: dict[str, Any]) -> tuple[bytes, str]:
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        for part in (candidate.get("content") or {}).get("parts") or []:
            if part.get("thought"):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if not inline or not inline.get("data"):
                continue
            try:
                return base64.b64decode(inline["data"], validate=True), inline.get(
                    "mimeType", inline.get("mime_type", "image/png")
                )
            except (binascii.Error, ValueError) as exc:
                raise ImageGenerationError("Gemini returned invalid image data.") from exc

    reason = ""
    if candidates:
        reason = candidates[0].get("finishReason") or candidates[0].get(
            "finish_reason", ""
        )
    detail = f" (finish reason: {reason})" if reason else ""
    raise ImageGenerationError(f"Gemini returned no final image{detail}.")


async def generate_image(
    prompt: str,
    references: list[tuple[bytes, str]],
) -> tuple[bytes, str]:
    if not IMAGE_API_KEY:
        raise ImageGenerationError(
            "Missing NANO_BANANA_PRO_API_KEY (or GEMINI_API_KEY) for Nano Banana Pro."
        )

    url = f"{IMAGE_BASE_URL.rstrip('/')}/{IMAGE_MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": _parts(prompt, references)}],
        "generationConfig": _generation_config(),
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": IMAGE_API_KEY}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=IMAGE_REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
            return _extract_image(response.json())
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code in {408, 409, 425, 429} or exc.response.status_code >= 500
            if attempt == MAX_RETRIES or not retryable:
                message = exc.response.text[:500]
                raise ImageGenerationError(
                    f"Nano Banana Pro failed with HTTP {exc.response.status_code}: {message}"
                ) from exc
        except httpx.RequestError as exc:
            if attempt == MAX_RETRIES:
                raise ImageGenerationError(f"Nano Banana Pro request failed: {exc}") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ImageGenerationError("Gemini returned an invalid response payload.") from exc

        await asyncio.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))

    raise ImageGenerationError("Nano Banana Pro request failed.")


def persist_generated_image(
    data: bytes,
    mime_type: str,
    *,
    conversation_id: str,
    step: int,
    public_backend_url: str,
) -> dict[str, Any]:
    LOCAL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_conversation_id = re.sub(r"[^A-Za-z0-9_-]", "", conversation_id)
    filename = (
        f"generated_{safe_conversation_id}_{step}_{uuid.uuid4().hex}"
        f"{_extension(mime_type)}"
    )
    path = LOCAL_IMAGE_DIR / filename
    path.write_bytes(data)
    return {
        "step": step,
        "url": f"{public_backend_url.rstrip('/')}/local-images/{quote(filename)}",
        "local_path": str(path),
        "mime_type": mime_type,
        "model": IMAGE_MODEL,
    }


async def execute_synthesis_plan(
    plan: dict[str, Any],
    *,
    source_image: bytes,
    source_mime_type: str,
    conversation_id: str,
    public_backend_url: str,
) -> AsyncIterator[dict[str, Any]]:
    previous: tuple[bytes, str] | None = None
    for step in plan["steps"]:
        references = [(source_image, source_mime_type)]
        if step.get("condition_on_previous_panel") and previous:
            references.append(previous)

        prompt = step["prompt"]
        if step.get("negative_prompt"):
            prompt += f"\n\nDo not include: {step['negative_prompt']}"
        image_data, mime_type = await generate_image(prompt, references)
        generated = persist_generated_image(
            image_data,
            mime_type,
            conversation_id=conversation_id,
            step=step["step"],
            public_backend_url=public_backend_url,
        )
        previous = (image_data, mime_type)
        yield generated
