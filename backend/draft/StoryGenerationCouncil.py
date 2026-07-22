from typing import List, Dict, Any, Tuple
import re
from .llm_client import query_models_parallel, query_model
from .config import COUNCIL_MEMBERS_STAGE1, CHAIRMAN_ID
from typing import Optional

class StoryGenerationCouncil:
    """
    Council system for folk painting story generation task.
    Has 3 stages:
    - Stage 1: Initial story generation from multiple models
    - Stage 2: Sequential completion/perfection of each story response
    - Stage 3: Evaluation and selection of the best story
    """

    def __init__(self):
        self.stage1_models = COUNCIL_MEMBERS_STAGE1
        self.chairman_model = CHAIRMAN_ID
        self.task_type = "story"

    async def run_task(
        self,
        user_query: str,
        image_description: str = "",
        image_data: Optional[bytes] = None,
        image_mime_type: str = "image/jpeg"
    ) -> Dict[str, Any]:
        """
        Run the complete 3-stage story generation process.
        """
        # Stage 1: Collect initial story responses
        stage1_results = await self._stage1_collect_responses(
            user_query, image_description, image_data, image_mime_type
        )

        if not stage1_results:
            return {
                "error": "All models failed to respond in stage 1",
                "stage1_results": [],
                "stage2_results": [],
                "final_result": None
            }

        # Stage 2: Sequentially complete each response
        stage2_results = await self._stage2_complete_responses(
            user_query, image_description, stage1_results, image_data, image_mime_type
        )

        # Stage 3: Evaluate and select the best
        final_result = await self._stage3_evaluate_and_select(
            user_query, image_description, stage2_results, image_data, image_mime_type
        )

        return {
            "stage1_results": stage1_results,
            "stage2_results": stage2_results,
            "final_result": final_result
        }

    async def _stage1_collect_responses(
        self, user_query: str, image_description: str,
        image_data: Optional[bytes], image_mime_type: str
    ) -> List[Dict[str, Any]]:
        """
        Stage 1: Collect initial story responses from multiple models.
        """
        prompt = f"""You are a storyteller specializing in folk painting narratives. Given the following description of a folk painting, create a four-frame story that brings the painting to life.

Painting Description: {image_description}

User Request: {user_query}

Create a four-frame story where each frame:
- Has a clear visual description
- Advances the narrative
- Maintains folk painting aesthetic
- Includes dialogue or narration

Format as:
Frame 1: [Description]
Frame 2: [Description]
Frame 3: [Description]
Frame 4: [Description]"""

        messages = [{"role": "user", "content": prompt}]

        # For story generation, we can optionally use image data if available
        responses = await query_models_parallel(
            self.stage1_models, messages, image_data=image_data, image_mime_type=image_mime_type
        )

        stage1_results = []
        for model_id, response in responses.items():
            if response is not None:
                stage1_results.append({
                    "model": model_id,
                    "response": response.get('content', ''),
                    "task_type": self.task_type
                })

        return stage1_results

    async def _stage2_complete_responses(
        self, user_query: str, image_description: str,
        stage1_results: List[Dict[str, Any]],
        image_data: Optional[bytes], image_mime_type: str
    ) -> List[Dict[str, Any]]:
        """
        Stage 2: Sequentially complete and perfect each story response from stage 1.
        """
        stage2_results = []

        for result in stage1_results:
            original_model = result['model']
            original_response = result['response']

            # Map stage 1 model to corresponding stage 2 model
            stage2_model = self._get_stage2_model(original_model)

            completion_prompt = f"""You are an expert folk painting storyteller. Review and complete the following four-frame story to make it perfect.

Original Painting Description: {image_description}
User Request: {user_query}

Initial Response from {original_model}:
{original_response}

Your task: Complete and perfect this four-frame story by:
1. Ensuring each frame has vivid, detailed descriptions
2. Creating smooth narrative progression
3. Maintaining folk painting aesthetic throughout
4. Adding meaningful dialogue or narration
5. Making the story emotionally engaging and complete

Provide the perfected four-frame story:"""

            messages = [{"role": "user", "content": completion_prompt}]

            # Query the corresponding stage 2 model (text-only for completion)
            response = await query_model(stage2_model, messages)

            if response is not None:
                stage2_results.append({
                    "original_model": original_model,
                    "stage2_model": stage2_model,
                    "original_response": original_response,
                    "perfected_response": response.get('content', ''),
                    "task_type": self.task_type
                })
            else:
                # If stage 2 fails, keep the original
                stage2_results.append({
                    "original_model": original_model,
                    "stage2_model": stage2_model,
                    "original_response": original_response,
                    "perfected_response": original_response,  # fallback
                    "task_type": self.task_type,
                    "error": "Stage 2 completion failed"
                })

        return stage2_results

    async def _stage3_evaluate_and_select(
        self, user_query: str, image_description: str,
        stage2_results: List[Dict[str, Any]],
        image_data: Optional[bytes], image_mime_type: str
    ) -> Dict[str, Any]:
        """
        Stage 3: Evaluate all perfected story responses and select the best one.
        """
        if not stage2_results:
            return {"error": "No responses to evaluate"}

        # Create evaluation prompt
        responses_text = "\n\n".join([
            f"Response {chr(65 + i)} (from {result['original_model']}):\n{result['perfected_response']}"
            for i, result in enumerate(stage2_results)
        ])

        evaluation_prompt = f"""You are an expert evaluator of folk painting stories. Evaluate the following four-frame stories and select the best one.

Original Painting Description: {image_description}
User Request: {user_query}

Responses to evaluate:
{responses_text}

Your task:
1. Evaluate each response based on:
   - Narrative coherence and progression
   - Folk painting aesthetic maintenance
   - Visual detail in each frame
   - Emotional engagement
   - Overall storytelling quality

2. At the end, clearly state your selection in this exact format:
BEST RESPONSE: Response X (where X is A, B, C, etc.)

Provide your evaluation and final selection:"""

        messages = [{"role": "user", "content": evaluation_prompt}]

        # Use chairman model for evaluation (text-only)
        response = await query_model(self.chairman_model, messages)

        if response is None:
            # Fallback: select the first response
            return {
                "selected_response": stage2_results[0]['perfected_response'],
                "selected_model": stage2_results[0]['original_model'],
                "evaluation": "Evaluation failed, selected first response as fallback",
                "task_type": self.task_type
            }

        evaluation_text = response.get('content', '')

        # Parse the best response selection
        best_response_label = self._parse_best_response_selection(evaluation_text)

        if best_response_label:
            # Convert label (A, B, C...) to index (0, 1, 2...)
            index = ord(best_response_label.upper()) - ord('A')
            if 0 <= index < len(stage2_results):
                selected = stage2_results[index]
                return {
                    "selected_response": selected['perfected_response'],
                    "selected_model": selected['original_model'],
                    "evaluation": evaluation_text,
                    "task_type": self.task_type
                }

        # Fallback if parsing fails
        return {
            "selected_response": stage2_results[0]['perfected_response'],
            "selected_model": stage2_results[0]['original_model'],
            "evaluation": evaluation_text,
            "task_type": self.task_type,
            "error": "Could not parse best response selection"
        }

    def _get_stage2_model(self, stage1_model: str) -> str:
        """
        Map stage 1 model to corresponding stage 2 model.
        """
        mapping = {
            "gpt_stage1": "gpt_stage2",
            "gemini_stage1": "gemini_stage2"
        }
        return mapping.get(stage1_model, stage1_model)  # fallback to same model

    def _parse_best_response_selection(self, evaluation_text: str) -> str:
        """
        Parse the BEST RESPONSE selection from evaluation text.
        """
        # Look for "BEST RESPONSE: Response X" pattern
        match = re.search(r'BEST RESPONSE:\s*Response\s*([A-Z])', evaluation_text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        return None
