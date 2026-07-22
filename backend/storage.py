import json
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import DATA_DIR

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def get_conversation_path(conversation_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", conversation_id):
        raise ValueError("Invalid conversation ID")
    return DATA_DIR / f"{conversation_id}.json"

def create_conversation(conversation_id: str) -> Dict[str, Any]:
    ensure_data_dir()
    conversation = {
        "id": conversation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": "New Session",
        "messages": []
    }
    save_conversation(conversation)
    return conversation

def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    path = get_conversation_path(conversation_id)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_conversation(conversation: Dict[str, Any]):
    ensure_data_dir()
    path = get_conversation_path(conversation['id'])
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(conversation, f, indent=2, ensure_ascii=False)

def list_conversations() -> List[Dict[str, Any]]:
    ensure_data_dir()
    conversations = []
    if DATA_DIR.exists():
        for path in DATA_DIR.iterdir():
            if path.suffix == '.json':
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        conversations.append({
                            "id": data["id"],
                            "created_at": data["created_at"],
                            "title": data.get("title", "New Conversation"),
                            "message_count": len(data["messages"])
                        })
                except Exception:
                    continue
    conversations.sort(key=lambda x: x["created_at"], reverse=True)
    return conversations

def add_user_message(
    conversation_id: str, 
    content: str, 
    image_url: Optional[str] = None,
    local_image_path: Optional[str] = None
):
    """
    Lưu tin nhắn User kèm Cloudinary URL và đường dẫn file Local.
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    message = {
        "role": "user",
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if image_url:
        message["image_url"] = image_url
    
    if local_image_path:
        message["local_image_path"] = local_image_path

    conversation["messages"].append(message)
    save_conversation(conversation)

def add_assistant_message(
    conversation_id: str,
    council_result: Dict[str, Any],
    task_type: str = "outpainting"
):
    """
    Lưu kết quả trả về từ Assistant (AI).
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    
    final = council_result.get("final_result") or {}
    display_content = final.get("selected_response") or final.get("response") or "Task completed."
    final_view = {
        "model": final.get("selected_model") or final.get("model") or "system",
        "response": display_content,
        **final,
    }
    message = {
        "role": "assistant",
        "content": display_content,
        "task_type": task_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # Persist the same shape emitted by SSE so a reloaded conversation renders
        # identically to a live one.
        "stage1": council_result.get("stage1_results", []),
        "stage2": council_result.get("stage2_results", []),
        "stage3": final_view,
        "council_response": council_result 
    }
    conversation["messages"].append(message)

    save_conversation(conversation)

def update_conversation_title(conversation_id: str, title: str):
    conversation = get_conversation(conversation_id)
    if conversation is None: return
    conversation["title"] = title
    save_conversation(conversation)
