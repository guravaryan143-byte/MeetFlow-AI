import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.agents.providers import AIProviderError, transcribe_audio


TIMESTAMP_SPEAKER_RE = re.compile(
    r"^(?:\[(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\]\s*)?(?P<speaker>[A-Za-z][A-Za-z0-9 ._-]{0,40}):\s*(?P<text>.+)$"
)


def _parse_timestamp_to_seconds(ts: Optional[str], fallback_seconds: float) -> float:
    if not ts:
        return fallback_seconds
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 2:
        return float(parts[0] * 60 + parts[1])
    if len(parts) == 3:
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    return fallback_seconds


def validate_upload_file(filename: str, size_bytes: int) -> Tuple[str, str]:
    """Validate uploaded audio or transcript file extension and size."""
    if not filename:
        raise ValueError("Filename is required.")
    ext = Path(filename).suffix.lower()
    if size_bytes <= 0:
        raise ValueError("Uploaded file is empty.")
    if size_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
        raise ValueError(
            f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB."
        )
    if ext in settings.ALLOWED_AUDIO_EXTENSIONS:
        return "audio", ext
    if ext in settings.ALLOWED_TRANSCRIPT_EXTENSIONS:
        return "transcript", ext
    allowed = sorted(settings.ALLOWED_AUDIO_EXTENSIONS | settings.ALLOWED_TRANSCRIPT_EXTENSIONS)
    raise ValueError(f"Unsupported file format '{ext}'. Allowed formats: {', '.join(allowed)}")


class TranscriptionAgent:
    """
    Agent 1: Transcription and Speaker Attribution.
    Supports Whisper-compatible transcription when an API key is configured,
    and deterministic speaker-diarized transcript parsing for text/VTT/SRT uploads.
    Never fabricates participant identities; unknown speakers are labeled 'Unknown Speaker'.
    """

    def transcribe_audio_or_text(
        self,
        raw_text: Optional[str] = None,
        audio_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        provider = "transcript_parser"

        if audio_path and not raw_text:
            if settings.TRANSCRIPTION_PROVIDER != "openai":
                raise AIProviderError(
                    "Audio transcription is unavailable in deterministic demo mode. "
                    "Set TRANSCRIPTION_PROVIDER=openai and configure an OpenAI transcription key."
                )
            raw_text, provider = transcribe_audio(audio_path)

        segments = self.parse_transcript_segments(raw_text or "")
        return {
            "provider": provider,
            "language": "en",
            "raw_text": raw_text or "",
            "segments": segments,
        }

    def parse_transcript_segments(self, raw_text: str) -> List[Dict[str, Any]]:
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        segments: List[Dict[str, Any]] = []
        current_sec = 0.0

        for idx, line in enumerate(lines):
            # Skip VTT/SRT cue headers and sequence numbers
            if line.upper() == "WEBVTT" or line.isdigit() or "-->" in line:
                continue

            match = TIMESTAMP_SPEAKER_RE.match(line)
            if match:
                ts_str = match.group("ts")
                raw_speaker = match.group("speaker").strip()
                text = match.group("text").strip()
                is_unknown = raw_speaker.lower() in {
                    "unknown", "unknown speaker", "speaker", "unidentified", ""
                } or bool(re.match(r"^speaker\s*\d+$", raw_speaker.lower()))
                speaker_label = "Unknown Speaker" if raw_speaker.lower() in {"unknown", "unidentified", ""} else raw_speaker
                start_time = _parse_timestamp_to_seconds(ts_str, current_sec)
                confidence = 0.72 if is_unknown else 0.94
            else:
                speaker_label = "Unknown Speaker"
                is_unknown = True
                text = line
                start_time = current_sec
                confidence = 0.65

            duration = max(3.0, round(len(text.split()) * 0.45, 1))
            end_time = round(start_time + duration, 1)
            current_sec = end_time

            segments.append(
                {
                    "segment_index": len(segments),
                    "speaker_key": speaker_label.lower().replace(" ", "_"),
                    "speaker_label": speaker_label,
                    "is_unknown": is_unknown,
                    "text": text,
                    "start_time": start_time,
                    "end_time": end_time,
                    "confidence": confidence,
                }
            )

        return segments
