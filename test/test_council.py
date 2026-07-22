from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.council import StructuredCouncil
from test.fixtures import outpainting_config


class CouncilInvariantTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_by_three_pipeline_builds_twelve_chairman_candidates(self):
        stage1_models = ["draft_a", "draft_b", "draft_c"]
        stage2_models = ["review_a", "review_b", "review_c"]
        council = StructuredCouncil(
            "outpainting",
            stage1_models=stage1_models,
            stage2_models=stage2_models,
            chairman_model="chairman",
        )

        stage1_response = {
            model: {
                "content": json.dumps(outpainting_config(model), ensure_ascii=False),
                "model_used": model,
                "provider": "mock",
                "attempts": 1,
            }
            for model in stage1_models
        }

        async def fake_query(model_id, messages, **kwargs):
            self.assertIn(
                "Expand exactly 512 pixels to the right", messages[0]["content"]
            )
            if model_id == "chairman":
                self.assertIn("Response L", messages[0]["content"])
                self.assertNotIn("review_c", messages[0]["content"])
                return {
                    "content": "All criteria checked.\nBEST RESPONSE: Response L",
                    "model_used": "chairman-model",
                    "provider": "mock",
                    "attempts": 1,
                }
            return {
                "content": json.dumps(
                    outpainting_config("anonymous-refinement"), ensure_ascii=False
                ),
                "model_used": model_id,
                "provider": "mock",
                "attempts": 1,
            }

        parallel_mock = AsyncMock(return_value=stage1_response)
        with patch(
            "backend.council.query_models_parallel",
            new=parallel_mock,
        ), patch("backend.council.query_model", new=fake_query):
            result = await council.run_task(
                "Expand exactly 512 pixels to the right",
                image_data=b"source",
                image_mime_type="image/png",
            )

        stage1_messages = parallel_mock.await_args.args[1]
        self.assertIn(
            "Expand exactly 512 pixels to the right",
            stage1_messages[0]["content"],
        )
        self.assertEqual(len(result["stage1_results"]), 3)
        self.assertEqual(len(result["stage2_results"]), 9)
        self.assertEqual(result["final_result"]["candidate_count"], 12)
        self.assertEqual(result["final_result"]["selected_label"], "L")
        self.assertEqual(result["final_result"]["selected_model"], "review_c")
        self.assertTrue(result["final_result"]["schema_valid"])
        self.assertEqual(
            result["final_result"]["synthesis_plan"]["expansion_settings"][
                "direction"
            ],
            "right",
        )

    async def test_refinement_failure_and_invalid_json_retain_original_slots(self):
        council = StructuredCouncil(
            "outpainting",
            stage1_models=["draft"],
            stage2_models=["failed_reviewer", "invalid_reviewer"],
            chairman_model="chairman",
        )
        original = json.dumps(outpainting_config(), ensure_ascii=False)
        stage1 = [
            {
                "model": "draft",
                "response": original,
                "schema_valid": True,
                "validation_errors": [],
            }
        ]
        mock_query = AsyncMock(
            side_effect=[
                None,
                {"content": "not JSON", "model_used": "invalid", "attempts": 1},
            ]
        )
        with patch("backend.council.query_model", new=mock_query):
            results = await council._stage2_complete_responses(
                "Expand right", stage1, None, b"source", "image/jpeg"
            )

        self.assertEqual(len(results), 2)
        self.assertTrue(all(item["fallback_used"] for item in results))
        self.assertTrue(all(item["perfected_response"] == original for item in results))
        self.assertTrue(all(item["schema_valid"] for item in results))

    def test_candidate_labels_extend_beyond_z(self):
        self.assertEqual(StructuredCouncil._label_for_index(0), "A")
        self.assertEqual(StructuredCouncil._label_for_index(25), "Z")
        self.assertEqual(StructuredCouncil._label_for_index(26), "AA")

    def test_selection_parser_requires_chairman_marker(self):
        self.assertEqual(
            StructuredCouncil._parse_best_response_selection(
                "Reasoning\nBEST RESPONSE: Response K"
            ),
            "K",
        )
        self.assertIsNone(
            StructuredCouncil._parse_best_response_selection("Response K seems nice")
        )


if __name__ == "__main__":
    unittest.main()
