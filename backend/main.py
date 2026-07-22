from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import storage
from .OutpaintingCouncil import OutpaintingCouncil
from .StoryGenerationCouncil import StoryGenerationCouncil
from .config import (
    CLOUDINARY_API_KEY,
    CLOUDINARY_API_SECRET,
    CLOUDINARY_CLOUD_NAME,
    LOCAL_IMAGE_DIR,
    MAX_UPLOAD_BYTES,
)
from .schemas import normalize_task_type
from .image_client import ImageGenerationError, execute_synthesis_plan
from .synthesis import InvalidSynthesisConfig, build_synthesis_plan

try:
    import cloudinary
    import cloudinary.uploader
except ImportError:  # Local-only storage remains fully functional.
    cloudinary = None


LOCAL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_BACKEND_URL = os.getenv("VIFA_PUBLIC_BACKEND_URL", "http://localhost:8000").rstrip("/")

if cloudinary and all(
    (CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)
):
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
    )

app = FastAPI(title="ViFA-Council API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "VIFA_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount(
    "/local-images",
    StaticFiles(directory=str(LOCAL_IMAGE_DIR)),
    name="local-images",
)

COUNCILS = {
    "outpainting": OutpaintingCouncil(),
    "story_generation": StoryGenerationCouncil(),
}

SUPPORTED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

OUTPAINTING_KEYWORDS = {
    "scale",
    "expand",
    "extend",
    "outpaint",
    "outpainting",
    "mở rộng",
    "vẽ thêm",
}
STORY_KEYWORDS = {
    "story",
    "comic",
    "panel",
    "narrative",
    "kể chuyện",
    "câu chuyện",
    "truyện",
    "khung truyện",
}


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New ViFA Task"


class ConversationMetadata(BaseModel):
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    id: str
    created_at: str
    title: str
    messages: list[dict[str, Any]]


def detect_task_type(content: str, explicit_task_type: str | None = None) -> str | None:
    if explicit_task_type:
        try:
            return normalize_task_type(explicit_task_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    query = content.casefold()
    if any(keyword in query for keyword in STORY_KEYWORDS):
        return "story_generation"
    if any(keyword in query for keyword in OUTPAINTING_KEYWORDS):
        return "outpainting"
    return None


def _sse(event_type: str, data: Any = None) -> str:
    payload: dict[str, Any] = {"type": event_type}
    if data is not None:
        payload["data"] = data
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _safe_filename(filename: str | None, mime_type: str) -> str:
    original = Path(filename or f"upload{SUPPORTED_IMAGE_TYPES[mime_type]}").name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original).stem).strip("._")
    stem = stem or "painting"
    return f"{uuid.uuid4()}_{stem}{SUPPORTED_IMAGE_TYPES[mime_type]}"


async def _save_upload(image: UploadFile) -> tuple[bytes, str, str, str]:
    mime_type = (image.content_type or "").split(";", 1)[0].strip().lower()
    if mime_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Upload JPEG, PNG, or WebP.",
        )

    image_data = await image.read(MAX_UPLOAD_BYTES + 1)
    if not image_data:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(image_data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    local_filename = _safe_filename(image.filename, mime_type)
    local_path = LOCAL_IMAGE_DIR / local_filename
    local_path.write_bytes(image_data)
    public_url = f"{PUBLIC_BACKEND_URL}/local-images/{quote(local_filename)}"

    if cloudinary and all(
        (CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)
    ):
        try:
            upload_result = await asyncio.to_thread(
                cloudinary.uploader.upload,
                image_data,
                folder="vifa_council/source_paintings",
                resource_type="image",
            )
            public_url = upload_result.get("secure_url", public_url)
        except Exception:
            # The local static URL is a deliberate, usable fallback.
            pass

    return image_data, mime_type, str(local_path), public_url


def _system_response(message: str, reason: str) -> dict[str, Any]:
    return {
        "model": "system",
        "response": message,
        "evaluation": reason,
        "schema_valid": False,
    }


def _load_conversation(conversation_id: str) -> dict[str, Any]:
    try:
        conversation = storage.get_conversation(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "ViFA-Council API",
        "tasks": sorted(COUNCILS),
    }


@app.get("/api/conversations", response_model=list[ConversationMetadata])
async def list_conversations() -> list[dict[str, Any]]:
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest) -> dict[str, Any]:
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    if request.title:
        storage.update_conversation_title(conversation_id, request.title)
        conversation["title"] = request.title
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str) -> dict[str, Any]:
    return _load_conversation(conversation_id)


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_and_process(
    conversation_id: str,
    content: str = Form(...),
    task_type: str | None = Form(None),
    image: UploadFile | None = File(None),
) -> StreamingResponse:
    conversation = _load_conversation(conversation_id)
    if not content.strip():
        raise HTTPException(status_code=422, detail="The user directive cannot be empty.")

    selected_task = detect_task_type(content, task_type)
    image_data: bytes | None = None
    image_mime_type = "image/jpeg"
    local_image_path: str | None = None
    image_url: str | None = None
    if image is not None:
        image_data, image_mime_type, local_image_path, image_url = await _save_upload(image)

    storage.add_user_message(
        conversation_id, content, image_url=image_url, local_image_path=local_image_path
    )
    if not conversation["messages"]:
        short_title = content if len(content) <= 45 else f"{content[:42]}..."
        storage.update_conversation_title(conversation_id, short_title)

    async def event_generator():
        yield _sse("start", {"task_type": selected_task})

        if selected_task is None or image_data is None:
            if image_data is None:
                message = (
                    "Please attach a Vietnamese folk-painting image so the Council "
                    "can analyze it."
                )
                reason = "A source image is required by both paper-defined tasks."
            else:
                message = (
                    "Please ask for either outpainting/expansion or an educational "
                    "story/comic so the correct Council schema can be selected."
                )
                reason = "No supported task intent was detected."
            final_payload = _system_response(message, reason)
            storage.add_assistant_message(
                conversation_id,
                {"stage1_results": [], "stage2_results": [], "final_result": final_payload},
                task_type="chat",
            )
            yield _sse("stage3_complete", final_payload)
            yield _sse("complete", {"task_type": selected_task})
            return

        council = COUNCILS[selected_task]
        try:
            yield _sse("stage1_start", {"task_type": selected_task})
            stage1_results = await council._stage1_collect_responses(
                content, image_url, image_data, image_mime_type
            )
            if not stage1_results:
                raise RuntimeError("All Stage-1 expert calls failed.")
            yield _sse("stage1_complete", stage1_results)

            yield _sse("stage2_start", {"task_type": selected_task})
            stage2_results = await council._stage2_complete_responses(
                content,
                stage1_results,
                image_url,
                image_data,
                image_mime_type,
            )
            yield _sse("stage2_complete", stage2_results)

            yield _sse("stage3_start", {"task_type": selected_task})
            final_result = await council._stage3_evaluate_and_select(
                content,
                stage2_results,
                image_url,
                image_data,
                image_mime_type,
                stage1_results=stage1_results,
            )
            final_payload = {
                "model": final_result.get("selected_model"),
                "response": final_result.get("selected_response"),
                **final_result,
            }
            yield _sse("stage3_complete", final_payload)

            generated_images: list[dict[str, Any]] = []
            synthesis_error: str | None = None
            selected_config = final_result.get("selected_config")
            if final_result.get("schema_valid") and selected_config:
                yield _sse("synthesis_start", {"model": os.getenv("IMAGE_MODEL", "gemini-3-pro-image")})
                try:
                    synthesis_plan = build_synthesis_plan(selected_task, selected_config)
                    async for generated in execute_synthesis_plan(
                        synthesis_plan,
                        source_image=image_data,
                        source_mime_type=image_mime_type,
                        conversation_id=conversation_id,
                        public_backend_url=PUBLIC_BACKEND_URL,
                    ):
                        generated_images.append(generated)
                        yield _sse("image_generated", generated)
                except (ImageGenerationError, InvalidSynthesisConfig) as exc:
                    synthesis_error = str(exc)
                    yield _sse("synthesis_error", {"message": synthesis_error})

                final_result["generated_images"] = generated_images
                final_result["synthesis_error"] = synthesis_error
                yield _sse(
                    "synthesis_complete",
                    {
                        "generated_images": generated_images,
                        "synthesis_error": synthesis_error,
                    },
                )

            storage.add_assistant_message(
                conversation_id,
                {
                    "task_type": selected_task,
                    "stage1_results": stage1_results,
                    "stage2_results": stage2_results,
                    "final_result": final_result,
                },
                task_type=selected_task,
            )
            yield _sse("complete", {"task_type": selected_task})
        except Exception as exc:
            error_message = str(exc) or type(exc).__name__
            storage.add_assistant_message(
                conversation_id,
                {
                    "final_result": {
                        "selected_response": error_message,
                        "selected_model": "system",
                        "evaluation": "Council execution failed.",
                    }
                },
                task_type="error",
            )
            yield _sse("error", {"message": error_message})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("VIFA_HOST", "127.0.0.1"),
        port=int(os.getenv("VIFA_PORT", "8000")),
    )
