import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.schemas.schemas import MeetingUnderstandingOutput


class AIProviderError(RuntimeError):
    pass


def _request_with_retry(method: str, url: str, **kwargs: Any) -> httpx.Response:
    for attempt in range(settings.AI_MAX_RETRIES + 1):
        try:
            response = httpx.request(
                method,
                url,
                timeout=settings.AI_TIMEOUT_SECONDS,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            if attempt == settings.AI_MAX_RETRIES:
                raise AIProviderError("The AI provider timed out. Please retry.") from exc
            time.sleep(min(0.5 * (2**attempt), 2))
            continue
        except httpx.RequestError as exc:
            if attempt == settings.AI_MAX_RETRIES:
                raise AIProviderError("The AI provider could not be reached.") from exc
            time.sleep(min(0.5 * (2**attempt), 2))
            continue

        if response.status_code == 429 or response.status_code >= 500:
            if attempt < settings.AI_MAX_RETRIES:
                time.sleep(min(0.5 * (2**attempt), 2))
                continue
        if not response.is_success:
            raise AIProviderError(
                f"The AI provider rejected the request (HTTP {response.status_code}). "
                "Check provider configuration and quota."
            )
        return response
    raise AIProviderError("The AI provider request failed after retries.")


def transcribe_audio(path: Path) -> Tuple[str, str]:
    api_key = settings.WHISPER_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        raise AIProviderError(
            "Audio transcription is not configured. Set WHISPER_API_KEY or OPENAI_API_KEY "
            "and TRANSCRIPTION_PROVIDER=openai."
        )
    try:
        with path.open("rb") as audio_file:
            response = _request_with_retry(
                "POST",
                settings.OPENAI_TRANSCRIPTION_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": settings.OPENAI_TRANSCRIPTION_MODEL, "response_format": "json"},
                files={"file": (path.name, audio_file)},
            )
        text = response.json().get("text")
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        raise AIProviderError("The transcription provider returned an invalid response.") from exc
    if not isinstance(text, str) or not text.strip():
        raise AIProviderError("The transcription provider returned no transcript.")
    return text.strip(), "openai_whisper"


def _prompt(meeting_title: str, segments: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    source = [
        {
            "segment_index": int(segment["segment_index"]),
            "speaker_label": segment.get("speaker_label", "Unknown Speaker"),
            "text": segment.get("text", ""),
        }
        for segment in segments
    ]
    instructions = (
        "Extract meeting facts conservatively. Return one JSON object with keys summary, topics, "
        "participants, decisions, action_items. Each decision must include subject, statement, "
        "decision_type (CONFIRMED, PROPOSED, REJECTED, SUPERSEDED, or UNRESOLVED), key_value, "
        "evidence_quote, source_segment_index, participants, confidence, needs_review. Each action "
        "item must include title, description, assigned_name, deadline, priority, dependencies, "
        "evidence_quote, source_segment_index, confidence, needs_review. Only CONFIRMED language "
        "may be classified CONFIRMED; suggestions remain PROPOSED. Never invent owners, deadlines, "
        "quotes, speakers, or decisions. Evidence quotes must be verbatim substrings of the cited "
        "segment. Use null when an owner or deadline is absent. Mark uncertain extractions for review."
    )
    return [
        {"role": "system", "content": instructions},
        {
            "role": "user",
            "content": json.dumps({"meeting_title": meeting_title, "segments": source}),
        },
    ]


def extract_with_provider(
    provider: str,
    meeting_title: str,
    segments: List[Dict[str, Any]],
    known_participants: Optional[List[str]] = None,
) -> Tuple[MeetingUnderstandingOutput, Dict[str, Any]]:
    messages = _prompt(meeting_title, segments)
    if known_participants:
        messages[1]["content"] = json.dumps(
            {
                "meeting_title": meeting_title,
                "known_participants": known_participants,
                "segments": [
                    {
                        "segment_index": int(segment["segment_index"]),
                        "speaker_label": segment.get("speaker_label", "Unknown Speaker"),
                        "text": segment.get("text", ""),
                    }
                    for segment in segments
                ],
            }
        )
    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise AIProviderError("Set OPENAI_API_KEY to use the OpenAI extraction provider.")
        response = _request_with_retry(
            "POST",
            settings.OPENAI_CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={
                "model": settings.OPENAI_MODEL,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("OpenAI returned an invalid structured response.") from exc
    elif provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise AIProviderError("Set GEMINI_API_KEY to use the Gemini extraction provider.")
        prompt = "\n\n".join(f"{message['role']}: {message['content']}" for message in messages)
        response = _request_with_retry(
            "POST",
            f"{settings.GEMINI_GENERATE_URL}/{settings.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
            },
        )
        try:
            body = response.json()
            content = body["candidates"][0]["content"]["parts"][0]["text"]
            usage = body.get("usageMetadata", {})
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("Gemini returned an invalid structured response.") from exc
    else:
        raise AIProviderError(f"Unsupported AI_PROVIDER '{provider}'.")

    try:
        data = json.loads(content)
        output = MeetingUnderstandingOutput.model_validate(data)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AIProviderError("The AI provider response did not match the extraction schema.") from exc

    source_by_index = {int(item["segment_index"]): item for item in segments}
    participant_names = {
        str(item.get("speaker_label", "")).casefold()
        for item in segments
        if item.get("speaker_label") and item.get("speaker_label") != "Unknown Speaker"
    }
    participant_names.update(name.casefold() for name in (known_participants or []))
    for decision in output.decisions:
        segment = source_by_index.get(decision.source_segment_index)
        if not segment or decision.evidence_quote not in str(segment.get("text", "")):
            raise AIProviderError("AI extraction included decision evidence not present in the transcript.")
    for action in output.action_items:
        segment = source_by_index.get(action.source_segment_index)
        if not segment or action.evidence_quote not in str(segment.get("text", "")):
            raise AIProviderError("AI extraction included task evidence not present in the transcript.")
        if action.assigned_name and action.assigned_name.casefold() not in participant_names:
            action.assigned_name = None
            action.needs_review = True
            action.confidence = min(action.confidence, 0.5)

    return output, {
        "provider": provider,
        "input_tokens": usage.get("prompt_tokens", usage.get("promptTokenCount")),
        "output_tokens": usage.get("completion_tokens", usage.get("candidatesTokenCount")),
    }
