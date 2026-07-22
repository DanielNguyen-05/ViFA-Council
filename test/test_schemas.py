from __future__ import annotations

import json
import unittest

from backend.schemas import extract_json_object, validate_candidate
from backend.synthesis import (
    InvalidSynthesisConfig,
    build_synthesis_plan,
)
from test.fixtures import outpainting_config, story_config


class SchemaTests(unittest.TestCase):
    def test_extracts_fenced_json(self):
        config = outpainting_config()
        raw = f"```json\n{json.dumps(config, ensure_ascii=False)}\n```"
        self.assertEqual(extract_json_object(raw), config)

    def test_validates_both_paper_contracts(self):
        self.assertTrue(
            validate_candidate("outpainting", outpainting_config())["schema_valid"]
        )
        self.assertTrue(
            validate_candidate("story", story_config())["schema_valid"]
        )

    def test_reports_missing_paper_fields(self):
        result = validate_candidate(
            "outpainting",
            {"task_type": "outpainting", "expansion_settings": {}},
        )
        self.assertFalse(result["schema_valid"])
        self.assertTrue(
            any("input_image_analysis" in error for error in result["validation_errors"])
        )

    def test_synthesis_rejects_unvalidated_text(self):
        with self.assertRaises(InvalidSynthesisConfig):
            build_synthesis_plan("outpainting", {"task_type": "outpainting"})

    def test_outpainting_plan_maps_spatial_and_blending_fields(self):
        plan = build_synthesis_plan(
            "outpainting", outpainting_config(), scenario_id="scenario_02"
        )
        self.assertEqual(plan["execution"], "single_image_edit")
        self.assertEqual(plan["selected_scenario_id"], "scenario_02")
        self.assertEqual(plan["expansion_settings"]["direction"], "right")
        self.assertIn("giấy điệp", plan["steps"][0]["prompt"])

    def test_story_plan_is_sequential_and_identity_conditioned(self):
        plan = build_synthesis_plan("story_generation", story_config())
        self.assertEqual(len(plan["steps"]), 4)
        self.assertFalse(plan["steps"][0]["condition_on_previous_panel"])
        self.assertTrue(plan["steps"][1]["condition_on_previous_panel"])
        self.assertEqual(
            plan["steps"][3]["shared_identity_context"]["characters"][0][
                "character_id"
            ],
            "char_01",
        )


if __name__ == "__main__":
    unittest.main()
