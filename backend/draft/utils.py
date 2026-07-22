from typing import List, Dict, Any, Tuple, Optional
import asyncio
import json
import re
from abc import ABC, abstractmethod
from .llm_client import query_models_parallel, query_model
from .config import COUNCIL_MEMBERS_STAGE1, PIPELINE_MAPPING, CHAIRMAN_ID

# --- BASE CLASS ---
class BaseCouncil(ABC):
    def __init__(self):
        self.stage1_models = COUNCIL_MEMBERS_STAGE1
        self.chairman_id = CHAIRMAN_ID
        self.pipeline_mapping = PIPELINE_MAPPING

    async def run_stage1(self, user_query: str, image_data: Optional[bytes] = None, mime_type: str = "image/jpeg") -> List[Dict[str, Any]]:
        """Stage 1: Ideation - Thu thập ý tưởng ban đầu"""
        messages = [
            {"role": "system", "content": self.get_stage1_system_prompt()},
            {"role": "user", "content": user_query}
        ]
        
        # Truyền image_data vào để model nhìn thấy ảnh (nếu có)
        responses = await query_models_parallel(
            self.stage1_models, messages, image_data=image_data, image_mime_type=mime_type
        )
        
        results = []
        for model_id, response in responses.items():
            if response:
                content = response.get('content', '')
                # Nếu subclass cần parse JSON, gọi hàm parse
                parsed_content = self.parse_response_content(content)
                results.append({
                    "model": model_id, 
                    "raw_response": content,
                    "parsed_response": parsed_content
                })
        return results

    async def run_stage2(self, user_query: str, stage1_results: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """Stage 2: Refinement - Hoàn thiện ý tưởng"""
        tasks = []
        task_info = []
        template = self.get_stage2_template()
        label_to_model = {} # Mapping để hiển thị UI (A -> GPT, B -> Gemini)

        for idx, result in enumerate(stage1_results):
            s1_model = result['model']
            concept = result['raw_response'] # Dùng raw text để refine
            s2_model = self.pipeline_mapping.get(s1_model, s1_model) # Fallback chính nó nếu không map

            # Gán nhãn A, B, C...
            label = chr(65 + idx)
            label_to_model[label] = f"{s1_model} -> {s2_model}"

            formatted_prompt = template.format(user_query=user_query, concept=concept)
            messages = [{"role": "user", "content": formatted_prompt}]
            
            tasks.append(query_model(s2_model, messages))
            task_info.append({
                "original_model": s1_model,
                "refiner_model": s2_model,
                "original_concept": concept,
                "label": label
            })

        responses_list = await asyncio.gather(*tasks)
        
        results = []
        for idx, response in enumerate(responses_list):
            info = task_info[idx]
            content = response.get('content', '') if response else info['original_concept'] # Fallback
            
            results.append({
                "label": info['label'],
                "original_model": info['original_model'],
                "refiner_model": info['refiner_model'],
                "refined_content": content,
                "parsed_content": self.parse_response_content(content)
            })
            
        return results, label_to_model

    async def run_stage3(self, user_query: str, stage2_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Stage 3: Selection - Chủ tịch chọn phương án tốt nhất"""
        candidates_text = ""
        for res in stage2_results:
            candidates_text += f"\n=== OPTION {res['label']} ({res['refiner_model']}) ===\n{res['refined_content']}\n"

        prompt = self.get_chairman_prompt(candidates_text, user_query)
        messages = [{"role": "user", "content": prompt}]
        response = await query_model(self.chairman_id, messages)

        if not response:
            return {"selected_label": "A", "rationale": "Chairman failed to respond.", "final_content": stage2_results[0]['refined_content']}
        
        chairman_text = response.get('content', '')
        
        # Parse lựa chọn của Chairman (Tìm chữ cái A, B, C...)
        match = re.search(r'BEST RESPONSE:.*([A-Z])', chairman_text, re.IGNORECASE)
        selected_label = match.group(1).upper() if match else "A"
        
        # Tìm content tương ứng
        selected_content = next((item['parsed_content'] for item in stage2_results if item['label'] == selected_label), None)
        if not selected_content: # Fallback nếu parse sai
             selected_content = stage2_results[0]['parsed_content']
             selected_label = "A"

        return {
            "selected_label": selected_label,
            "rationale": chairman_text,
            "final_content": selected_content
        }

    def parse_response_content(self, content: str) -> Any:
        """Hàm helper để parse JSON từ response nếu cần. Mặc định trả về string."""
        return content

    @abstractmethod
    def get_stage1_system_prompt(self) -> str: pass
    @abstractmethod
    def get_stage2_template(self) -> str: pass
    @abstractmethod
    def get_chairman_prompt(self, candidates_text: str, user_query: str) -> str: pass


# --- IMPLEMENTATION 1: OUTPAINTING COUNCIL ---
class OutpaintingCouncil(BaseCouncil):
    """
    Hội đồng chuyên xử lý mở rộng tranh (Outpainting) trả về JSON cấu trúc.
    """
    def parse_response_content(self, content: str) -> Any:
        """Cố gắng trích xuất và parse JSON từ response"""
        try:
            # Tìm block json hoặc lấy toàn bộ text
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            text_to_parse = json_match.group(0) if json_match else content
            return json.loads(text_to_parse)
        except:
            return content # Trả về text gốc nếu lỗi

    def get_stage1_system_prompt(self) -> str:
        return """You are a folk art vision expert. 
Return ONLY valid JSON (no markdown, no extra text).
I want to scale/expand this image using outpainting. Fill this template:
{
  "task_type": "outpainting",
  "input_image_meaning": "Describe the input image",
  "expansion_settings": { "direction": "all", "pixel_amount": 256, "mask_blur": 4 },
  "context_awareness": { "original_style": "", "seamless_blending_keywords": [] },
  "scenarios": [
    { "scenario_id": "1", "description": "", "prompt": "" },
    { "scenario_id": "2", "description": "", "prompt": "" }
  ]
}"""

    def get_stage2_template(self) -> str:
        return """You are an expert Outpainting Refiner. Fix and perfect the following JSON.
        
User Request: {user_query}
Draft JSON: {concept}

Task:
1. Ensure JSON validity.
2. Enrich the prompts in 'scenarios'.
3. Ensure 'expansion_settings' are optimal.

Return ONLY the perfected JSON."""

    def get_chairman_prompt(self, candidates_text: str, user_query: str) -> str:
        return f"""Act as the Chief Curator. Select the best Outpainting JSON configuration.

User Request: {user_query}

Candidates:
{candidates_text}

Selection Format:
1. Critique each option briefly.
2. Conclusion: "BEST RESPONSE: X" (where X is the Option Label)."""


# --- IMPLEMENTATION 2: COMIC COUNCIL ---
class ComicCouncil(BaseCouncil):
    """
    Hội đồng chuyên vẽ truyện tranh 4 khung từ 1 ảnh/ý tưởng.
    """
    def get_stage1_system_prompt(self) -> str:
        return """Bạn là nhà biên kịch truyện tranh dân gian.
Từ hình ảnh hoặc ý tưởng, hãy sáng tạo cốt truyện ngắn 4 hồi (4 khung).
Giữ văn phong mộc mạc, hài hước."""

    def get_stage2_template(self) -> str:
        return """Chuyển cốt truyện sau thành kịch bản vẽ (Image Prompts) chi tiết cho 4 Panel.
        
Cốt truyện: {concept}

Output Markdown:
# Panel 1
- Visual: ...
- Prompt (English): ...
- Caption: ...
... (Panel 2, 3, 4)"""

    def get_chairman_prompt(self, candidates_text: str, user_query: str) -> str:
        return f"""Chọn kịch bản truyện tranh hấp dẫn nhất.
        
Candidates:
{candidates_text}

Conclusion: "BEST RESPONSE: X" """


# --- IMPLEMENTATION 3: GENERAL CHAT COUNCIL ---
class GeneralChatCouncil(BaseCouncil):
    def get_stage1_system_prompt(self) -> str:
        return "You are a helpful assistant. Provide a comprehensive answer."
    def get_stage2_template(self) -> str:
        return "Review and improve this answer: {concept}. Make it more accurate and concise."
    def get_chairman_prompt(self, candidates, query) -> str:
        return f"Select the best answer for '{query}' from:\n{candidates}\nConclusion: 'BEST RESPONSE: X'"


# --- FACTORY / ROUTER ---
def get_council(user_query: str) -> BaseCouncil:
    """Tự động chọn loại hội đồng dựa trên từ khóa"""
    q_lower = user_query.lower()
    
    # Logic phát hiện intent
    if any(k in q_lower for k in ["scale", "expand", "outpainting", "mở rộng", "vẽ thêm"]):
        return OutpaintingCouncil()
    elif any(k in q_lower for k in ["comic", "truyện", "kể chuyện", "4 khung"]):
        return ComicCouncil()
    
    return GeneralChatCouncil()

# --- HELPER FOR MAIN.PY (Tạo title) ---
async def generate_conversation_title(content: str) -> str:
    """Hàm phụ trợ tạo tiêu đề ngắn gọn"""
    messages = [{"role": "user", "content": f"Summarize this into a short 3-5 word title: {content}"}]
    # Dùng chairman model cho rẻ/nhanh hoặc model nào cũng được
    resp = await query_model(CHAIRMAN_ID, messages)
    if resp:
        return resp.get('content', 'New Conversation').strip().strip('"')
    return "New Conversation"