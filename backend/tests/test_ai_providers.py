import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.providers import AIProviderError, extract_with_provider, transcribe_audio
from app.core.config import settings


class AIProviderTests(unittest.TestCase):
    def setUp(self):
        self.segment = {
            "segment_index": 0,
            "speaker_label": "Jordan Lee",
            "text": "The launch date is confirmed as December 10.",
        }
        self.data = {
            "summary": "The team confirmed a launch date.",
            "topics": ["Product Launch Date"],
            "participants": ["Jordan Lee"],
            "decisions": [
                {
                    "subject": "Product Launch Date",
                    "statement": self.segment["text"],
                    "decision_type": "CONFIRMED",
                    "key_value": "December 10",
                    "evidence_quote": self.segment["text"],
                    "source_segment_index": 0,
                    "participants": ["Jordan Lee"],
                    "confidence": 0.9,
                    "needs_review": False,
                }
            ],
            "action_items": [],
        }

    def test_openai_structured_response_and_usage(self):
        response = httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(self.data)}}],
                "usage": {"prompt_tokens": 24, "completion_tokens": 8},
            },
        )
        with patch.object(settings, "OPENAI_API_KEY", "test-key"), patch(
            "app.agents.providers._request_with_retry", return_value=response
        ) as request:
            output, usage = extract_with_provider("openai", "Planning", [self.segment])
        self.assertEqual(output.decisions[0].decision_type, "CONFIRMED")
        self.assertEqual(usage, {"provider": "openai", "input_tokens": 24, "output_tokens": 8})
        self.assertEqual(request.call_args.args[0], "POST")

    def test_gemini_structured_response_and_usage(self):
        response = httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(self.data)}]}}],
                "usageMetadata": {"promptTokenCount": 17, "candidatesTokenCount": 9},
            },
        )
        with patch.object(settings, "GEMINI_API_KEY", "test-key"), patch(
            "app.agents.providers._request_with_retry", return_value=response
        ) as request:
            _, usage = extract_with_provider("gemini", "Planning", [self.segment])
        self.assertEqual(usage["input_tokens"], 17)
        self.assertEqual(usage["output_tokens"], 9)
        self.assertEqual(request.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")
        self.assertNotIn("test-key", request.call_args.args[1])

    def test_provider_evidence_must_match_transcript(self):
        bad_data = dict(self.data)
        bad_data["decisions"] = [dict(self.data["decisions"][0], evidence_quote="invented quote")]
        response = httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(bad_data)}}]}
        )
        with patch.object(settings, "OPENAI_API_KEY", "test-key"), patch(
            "app.agents.providers._request_with_retry", return_value=response
        ):
            with self.assertRaisesRegex(AIProviderError, "evidence not present"):
                extract_with_provider("openai", "Planning", [self.segment])

    def test_audio_transcription_uses_mocked_whisper_provider(self):
        response = httpx.Response(200, json={"text": "We confirmed the launch date."})
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "recording.wav"
            audio.write_bytes(b"audio")
            with patch.object(settings, "WHISPER_API_KEY", "test-key"), patch(
                "app.agents.providers._request_with_retry", return_value=response
            ) as request:
                text, provider = transcribe_audio(audio)
        self.assertEqual(text, "We confirmed the launch date.")
        self.assertEqual(provider, "openai_whisper")
        self.assertIn("files", request.call_args.kwargs)

    def test_audio_transcription_fails_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "recording.wav"
            audio.write_bytes(b"audio")
            with patch.object(settings, "WHISPER_API_KEY", ""), patch.object(
                settings, "OPENAI_API_KEY", ""
            ):
                with self.assertRaisesRegex(AIProviderError, "not configured"):
                    transcribe_audio(audio)

    def test_transient_provider_responses_are_retried(self):
        first = httpx.Response(503)
        second = httpx.Response(200, json={"ok": True})
        with patch.object(settings, "AI_MAX_RETRIES", 1), patch(
            "app.agents.providers.httpx.request", side_effect=[first, second]
        ) as request, patch("app.agents.providers.time.sleep"):
            result = __import__("app.agents.providers", fromlist=["_request_with_retry"])._request_with_retry(
                "GET", "https://provider.test"
            )
        self.assertTrue(result.is_success)
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
