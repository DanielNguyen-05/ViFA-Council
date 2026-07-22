from __future__ import annotations

import asyncio
import base64
import logging
import random
from copy import deepcopy
from typing import Any, Optional

import httpx

from .config import (
    MAX_RETRIES,
    MODEL_REGISTRY,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BASE_DELAY_SECONDS,
)

logger = logging.getLogger(__name__)


async def query_model(
    model_id: str,
    messages: list[dict[str, Any]],
    timeout: float | None = None,
    retries: int | None = None,
    image_data: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    image_url: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Query one configured model with paper-aligned transient retries."""

    config = MODEL_REGISTRY.get(model_id)
    if not config:
        logger.error("Unknown model ID %s", model_id)
        return None
    if not config.get("api_key"):
        logger.error("No API key configured for model ID %s", model_id)
        return None

    provider = config["provider"]
    timeout = timeout if timeout is not None else REQUEST_TIMEOUT_SECONDS
    retries = retries if retries is not None else MAX_RETRIES
    retries = max(1, retries)

    if image_url and not image_data and provider in {"google", "anthropic"}:
        image_data, image_mime_type = await _download_image_from_url(image_url)

    for attempt in range(1, retries + 1):
        try:
            if provider == "openai":
                result = await _call_openai_style(
                    config,
                    messages,
                    timeout,
                    image_url=image_url,
                    image_data=image_data,
                    image_mime_type=image_mime_type,
                )
            elif provider == "google":
                result = await _call_google_rest(
                    config, messages, timeout, image_data, image_mime_type
                )
            elif provider == "anthropic":
                result = await _call_anthropic_rest(
                    config, messages, timeout, image_data, image_mime_type
                )
            else:
                logger.error("Unsupported provider %s for %s", provider, model_id)
                return None

            result.update(
                {
                    "attempts": attempt,
                    "provider": provider,
                    "registry_id": model_id,
                }
            )
            return result
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if attempt == retries or not _is_retryable_status(status):
                logger.error("%s failed with HTTP %s", model_id, status)
                return None
            await _retry_delay(model_id, attempt, status)
        except (httpx.RequestError, TimeoutError) as exc:
            if attempt == retries:
                logger.error("%s request failed: %s", model_id, exc)
                return None
            await _retry_delay(model_id, attempt, type(exc).__name__)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.error("%s returned an invalid provider payload: %s", model_id, exc)
            return None
        except Exception as exc:
            # Keep one provider's unexpected SDK/transport failure from
            # cancelling the other parallel Council slots.
            logger.exception("Unexpected failure while querying %s: %s", model_id, exc)
            return None

    return None


def _is_retryable_status(status: int) -> bool:
    return status in {408, 409, 425, 429} or status >= 500


async def _retry_delay(model_id: str, attempt: int, reason: Any) -> None:
    base = RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
    wait_time = base + random.uniform(0, max(0.05, base * 0.25))
    logger.warning(
        "%s transient failure (%s); retrying in %.2fs", model_id, reason, wait_time
    )
    await asyncio.sleep(wait_time)


async def _download_image_from_url(url: str) -> tuple[Optional[bytes], str]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=20.0)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "image/jpeg")
            return response.content, content_type.split(";", 1)[0].strip()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Could not download source image from %s: %s", url, exc)
        return None, "image/jpeg"


def _build_openai_messages(
    messages: list[dict[str, Any]],
    *,
    image_url: str | None = None,
    image_data: bytes | None = None,
    image_mime_type: str = "image/jpeg",
) -> list[dict[str, Any]]:
    """Preserve text-only messages and attach an image to the last user turn."""

    final_messages = deepcopy(messages)
    if not image_url and not image_data:
        return final_messages

    user_index = next(
        (index for index in range(len(final_messages) - 1, -1, -1)
         if final_messages[index].get("role") == "user"),
        None,
    )
    if user_index is None:
        final_messages.append({"role": "user", "content": "Analyze this image."})
        user_index = len(final_messages) - 1

    current_content = final_messages[user_index].get("content", "")
    if isinstance(current_content, list):
        content_payload = deepcopy(current_content)
    else:
        content_payload = [{"type": "text", "text": str(current_content)}]

    # Prefer caller-supplied bytes. A local fallback URL is useful to the web
    # UI but is not reachable from a hosted model provider.
    if image_data is not None:
        encoded = base64.b64encode(image_data or b"").decode("utf-8")
        encoded_url = f"data:{image_mime_type};base64,{encoded}"
    else:
        encoded_url = image_url
    content_payload.append(
        {
            "type": "image_url",
            "image_url": {"url": encoded_url, "detail": "auto"},
        }
    )
    final_messages[user_index]["content"] = content_payload
    return final_messages


async def _call_openai_style(
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    timeout: float,
    *,
    image_url: str | None = None,
    image_data: bytes | None = None,
    image_mime_type: str = "image/jpeg",
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": _build_openai_messages(
            messages,
            image_url=image_url,
            image_data=image_data,
            image_mime_type=image_mime_type,
        ),
        "temperature": config.get("temperature", 0.7),
        "max_tokens": config.get("max_output_tokens", 16_384),
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(config["base_url"], headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return {
        "content": data["choices"][0]["message"]["content"],
        "model_used": config["model"],
    }


def _build_google_payload(
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    image_data: bytes | None,
    image_mime_type: str,
) -> dict[str, Any]:
    system_parts = [
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "system"
    ]
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        google_role = "model" if role == "assistant" else "user"
        contents.append(
            {"role": google_role, "parts": [{"text": str(message.get("content", ""))}]}
        )

    if not contents:
        contents.append({"role": "user", "parts": [{"text": "Analyze the image."}]})

    if image_data:
        encoded = base64.b64encode(image_data).decode("utf-8")
        last_user = next(
            (item for item in reversed(contents) if item["role"] == "user"), None
        )
        if last_user is None:
            last_user = {"role": "user", "parts": []}
            contents.append(last_user)
        last_user["parts"].insert(
            0,
            {
                "inline_data": {
                    "mime_type": image_mime_type,
                    "data": encoded,
                }
            },
        )

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": config.get("temperature", 0.7),
            "maxOutputTokens": config.get("max_output_tokens", 16_384),
        },
    }
    if system_parts:
        payload["system_instruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return payload


async def _call_google_rest(
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    timeout: float,
    image_data: bytes | None = None,
    image_mime_type: str = "image/jpeg",
) -> dict[str, Any]:
    url = f"{config['base_url']}/{config['model']}:generateContent"
    payload = _build_google_payload(
        config, messages, image_data=image_data, image_mime_type=image_mime_type
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers={"Content-Type": "application/json"},
            params={"key": config["api_key"]},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    parts = data["candidates"][0]["content"]["parts"]
    content = "\n".join(part["text"] for part in parts if part.get("text"))
    return {"content": content, "model_used": config["model"]}


def _build_anthropic_payload(
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    image_data: bytes | None,
    image_mime_type: str,
) -> dict[str, Any]:
    system_text = "\n\n".join(
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "system"
    )
    anthropic_messages: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "system":
            continue
        role = "assistant" if message.get("role") == "assistant" else "user"
        anthropic_messages.append(
            {
                "role": role,
                "content": [{"type": "text", "text": str(message.get("content", ""))}],
            }
        )
    if not anthropic_messages:
        anthropic_messages.append(
            {"role": "user", "content": [{"type": "text", "text": "Analyze the image."}]}
        )

    if image_data:
        encoded = base64.b64encode(image_data).decode("utf-8")
        last_user = next(
            (item for item in reversed(anthropic_messages) if item["role"] == "user"),
            None,
        )
        if last_user is None:
            last_user = {"role": "user", "content": []}
            anthropic_messages.append(last_user)
        last_user["content"].insert(
            0,
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_mime_type,
                    "data": encoded,
                },
            },
        )

    payload: dict[str, Any] = {
        "model": config["model"],
        "messages": anthropic_messages,
        "temperature": config.get("temperature", 0.7),
        "max_tokens": config.get("max_output_tokens", 16_384),
    }
    if system_text:
        payload["system"] = system_text
    return payload


async def _call_anthropic_rest(
    config: dict[str, Any],
    messages: list[dict[str, Any]],
    timeout: float,
    image_data: bytes | None = None,
    image_mime_type: str = "image/jpeg",
) -> dict[str, Any]:
    headers = {
        "x-api-key": config["api_key"],
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = _build_anthropic_payload(
        config, messages, image_data=image_data, image_mime_type=image_mime_type
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(config["base_url"], headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = "\n".join(
        block["text"] for block in data["content"] if block.get("type") == "text"
    )
    return {"content": content, "model_used": config["model"]}


async def query_models_parallel(
    model_ids: list[str],
    messages: list[dict[str, Any]],
    image_data: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    image_url: Optional[str] = None,
) -> dict[str, Optional[dict[str, Any]]]:
    tasks = [
        query_model(
            model_id,
            messages,
            image_data=image_data,
            image_mime_type=image_mime_type,
            image_url=image_url,
        )
        for model_id in model_ids
    ]
    responses = await asyncio.gather(*tasks)
    return dict(zip(model_ids, responses))
