from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.llm_client import (
    _build_anthropic_payload,
    _build_google_payload,
    _build_openai_messages,
    query_model,
)


class ProviderPayloadTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "model": "test-model",
            "temperature": 0.7,
            "max_output_tokens": 100,
        }

    def test_openai_text_only_keeps_messages(self):
        messages = [{"role": "user", "content": "Chairman prompt"}]
        self.assertEqual(_build_openai_messages(messages), messages)

    def test_openai_preserves_image_mime_type(self):
        messages = [{"role": "user", "content": "Analyze"}]
        built = _build_openai_messages(
            messages, image_data=b"png", image_mime_type="image/png"
        )
        image_url = built[0]["content"][1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/png;base64,"))

    def test_openai_prefers_bytes_over_unreachable_local_url(self):
        built = _build_openai_messages(
            [{"role": "user", "content": "Analyze"}],
            image_url="http://localhost:8000/local-images/source.png",
            image_data=b"png",
            image_mime_type="image/png",
        )
        image_url = built[0]["content"][1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/png;base64,"))

    def test_google_preserves_system_and_all_turns(self):
        payload = _build_google_payload(
            self.config,
            [
                {"role": "system", "content": "Cultural constraints"},
                {"role": "user", "content": "First"},
                {"role": "assistant", "content": "Draft"},
                {"role": "user", "content": "Refine"},
            ],
            image_data=b"image",
            image_mime_type="image/webp",
        )
        self.assertEqual(payload["system_instruction"]["parts"][0]["text"], "Cultural constraints")
        self.assertEqual([item["role"] for item in payload["contents"]], ["user", "model", "user"])
        self.assertEqual(
            payload["contents"][-1]["parts"][0]["inline_data"]["mime_type"],
            "image/webp",
        )

    def test_anthropic_payload_has_multimodal_user_content(self):
        payload = _build_anthropic_payload(
            self.config,
            [{"role": "user", "content": "Analyze"}],
            image_data=b"image",
            image_mime_type="image/jpeg",
        )
        self.assertEqual(payload["messages"][0]["content"][0]["type"], "image")
        self.assertEqual(payload["messages"][0]["content"][1]["type"], "text")


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_status_retries_up_to_success(self):
        config = {
            "provider": "openai",
            "model": "mock-model",
            "api_key": "test-key",
            "base_url": "https://example.test",
        }
        request = httpx.Request("POST", "https://example.test")
        transient = httpx.HTTPStatusError(
            "rate limited",
            request=request,
            response=httpx.Response(429, request=request),
        )
        provider_call = AsyncMock(
            side_effect=[
                transient,
                transient,
                {"content": "ok", "model_used": "mock-model"},
            ]
        )
        with patch.dict("backend.llm_client.MODEL_REGISTRY", {"mock": config}), patch(
            "backend.llm_client._call_openai_style", new=provider_call
        ), patch("backend.llm_client._retry_delay", new=AsyncMock()) as delay:
            result = await query_model(
                "mock", [{"role": "user", "content": "test"}], retries=3
            )

        self.assertEqual(provider_call.await_count, 3)
        self.assertEqual(delay.await_count, 2)
        self.assertEqual(result["content"], "ok")
        self.assertEqual(result["attempts"], 3)

    async def test_non_transient_status_does_not_retry(self):
        config = {
            "provider": "openai",
            "model": "mock-model",
            "api_key": "test-key",
            "base_url": "https://example.test",
        }
        request = httpx.Request("POST", "https://example.test")
        bad_request = httpx.HTTPStatusError(
            "bad request",
            request=request,
            response=httpx.Response(400, request=request),
        )
        provider_call = AsyncMock(side_effect=bad_request)
        with patch.dict("backend.llm_client.MODEL_REGISTRY", {"mock": config}), patch(
            "backend.llm_client._call_openai_style", new=provider_call
        ), patch("backend.llm_client._retry_delay", new=AsyncMock()) as delay:
            result = await query_model(
                "mock", [{"role": "user", "content": "test"}], retries=3
            )

        self.assertIsNone(result)
        self.assertEqual(provider_call.await_count, 1)
        delay.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
