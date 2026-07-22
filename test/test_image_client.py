from __future__ import annotations

import base64
import unittest

from backend.image_client import ImageGenerationError, _extract_image, _generation_config


class ImageClientTests(unittest.TestCase):
    def test_extracts_non_thought_inline_image(self):
        encoded = base64.b64encode(b"generated-image").decode("ascii")
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"thought": True, "inlineData": {"data": encoded}},
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": encoded,
                                }
                            },
                        ]
                    }
                }
            ]
        }
        data, mime_type = _extract_image(payload)
        self.assertEqual(data, b"generated-image")
        self.assertEqual(mime_type, "image/png")

    def test_reports_missing_final_image(self):
        with self.assertRaises(ImageGenerationError):
            _extract_image({"candidates": [{"finishReason": "SAFETY"}]})

    def test_generation_config_requests_image_output(self):
        self.assertEqual(_generation_config()["responseModalities"], ["IMAGE"])


if __name__ == "__main__":
    unittest.main()
