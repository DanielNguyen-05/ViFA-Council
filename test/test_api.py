from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main, storage
from test.fixtures import outpainting_config


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        data_lines = [line.removeprefix("data: ") for line in block.splitlines() if line.startswith("data: ")]
        if data_lines:
            events.append(json.loads("\n".join(data_lines)))
    return events


class FakeCouncil:
    async def _stage1_collect_responses(self, *args, **kwargs):
        return [
            {
                "model": "mock_stage1",
                "response": json.dumps(outpainting_config(), ensure_ascii=False),
                "schema_valid": True,
                "validation_errors": [],
            }
        ]

    async def _stage2_complete_responses(self, *args, **kwargs):
        return [
            {
                "source_draft_index": 0,
                "original_model": "mock_stage1",
                "stage2_model": "mock_stage2",
                "original_response": json.dumps(outpainting_config(), ensure_ascii=False),
                "perfected_response": json.dumps(outpainting_config(), ensure_ascii=False),
                "schema_valid": True,
                "validation_errors": [],
                "fallback_used": False,
            }
        ]

    async def _stage3_evaluate_and_select(self, *args, **kwargs):
        config = outpainting_config()
        return {
            "selected_response": json.dumps(config, ensure_ascii=False),
            "selected_config": config,
            "selected_model": "mock_stage2",
            "selected_stage": "Stage 2 (Cross-refined)",
            "selected_label": "B",
            "schema_valid": True,
            "validation_errors": [],
            "evaluation": "BEST RESPONSE: Response B",
            "candidate_count": 2,
            "task_type": "outpainting",
        }


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.data_patch = patch.object(storage, "DATA_DIR", root / "conversations")
        self.image_patch = patch.object(main, "LOCAL_IMAGE_DIR", root / "images")
        self.data_patch.start()
        self.image_patch.start()
        main.LOCAL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.client = TestClient(main.app)

    def tearDown(self):
        self.image_patch.stop()
        self.data_patch.stop()
        self.temp_dir.cleanup()

    def create_conversation(self) -> str:
        response = self.client.post("/api/conversations", json={})
        self.assertEqual(response.status_code, 200)
        return response.json()["id"]

    def test_stream_endpoint_keeps_sse_contract_when_image_is_missing(self):
        conversation_id = self.create_conversation()
        response = self.client.post(
            f"/api/conversations/{conversation_id}/message/stream",
            data={"content": "Create a four-panel educational story"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = parse_sse(response.text)
        self.assertEqual(
            [event["type"] for event in events],
            ["start", "stage3_complete", "complete"],
        )
        self.assertIn("source image", events[1]["data"]["evaluation"])

        stored = self.client.get(f"/api/conversations/{conversation_id}").json()
        self.assertEqual(stored["messages"][-1]["stage3"]["model"], "system")

    def test_mocked_outpainting_stream_persists_live_stage_shape(self):
        conversation_id = self.create_conversation()
        with patch.dict(main.COUNCILS, {"outpainting": FakeCouncil()}):
            response = self.client.post(
                f"/api/conversations/{conversation_id}/message/stream",
                data={"content": "Expand 512 pixels to the right"},
                files={"image": ("painting.png", b"mock-png", "image/png")},
            )
        self.assertEqual(response.status_code, 200)
        events = parse_sse(response.text)
        self.assertEqual(
            [event["type"] for event in events],
            [
                "start",
                "stage1_start",
                "stage1_complete",
                "stage2_start",
                "stage2_complete",
                "stage3_start",
                "stage3_complete",
                "synthesis_start",
                "synthesis_error",
                "synthesis_complete",
                "complete",
            ],
        )
        self.assertEqual(events[6]["data"]["model"], "mock_stage2")

        stored = self.client.get(f"/api/conversations/{conversation_id}").json()
        assistant = stored["messages"][-1]
        self.assertEqual(assistant["task_type"], "outpainting")
        self.assertEqual(assistant["stage1"][0]["model"], "mock_stage1")
        self.assertEqual(assistant["stage2"][0]["stage2_model"], "mock_stage2")
        self.assertEqual(assistant["stage3"]["model"], "mock_stage2")
        self.assertIn("NANO_BANANA_PRO_API_KEY", assistant["stage3"]["synthesis_error"])

    def test_rejects_unsupported_upload_type_before_writing(self):
        conversation_id = self.create_conversation()
        response = self.client.post(
            f"/api/conversations/{conversation_id}/message/stream",
            data={"content": "Expand this image"},
            files={"image": ("painting.gif", b"gif", "image/gif")},
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(list(main.LOCAL_IMAGE_DIR.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
