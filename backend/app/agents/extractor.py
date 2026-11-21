import re
from typing import Any, Dict, List, Optional

from app.schemas.schemas import (
    ExtractedActionItem,
    ExtractedDecision,
    MeetingUnderstandingOutput,
)
from app.agents.providers import extract_with_provider
from app.core.config import settings

DATE_PATTERN = re.compile(
    r"\b("
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?"
    r"|\d{4}-\d{2}-\d{2}"
    r"|Q[1-4]\s+\d{4}"
    r"|(?:next\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
    r"|end of (?:the )?(?:week|month|quarter)"
    r")\b",
    re.IGNORECASE,
)

CONFIRMED_CUES = (
    "confirmed", "decided", "agreed", "approved", "finalized", "locked in",
    "we will launch", "is set for", "is confirmed as", "we're going with",
    "official date", "decision:", "approved:"
)
PROPOSED_CUES = (
    "propose", "proposing", "proposal", "suggest", "suggesting", "what if we",
    "should we move", "push to", "move to", "delay to", "shift to", "recommend",
    "could we", "might want to", "consider moving"
)
REJECTED_CUES = (
    "rejected", "decided against", "won't do", "will not do", "ruled out",
    "declined", "vetoed", "not going with"
)
ACTION_CUES = (
    "action item", "will own", "will handle", "will prepare", "will send",
    "will build", "will create", "will update", "will review", "will draft",
    "will finalize", "needs to", "need to", "please ", "assigned to", "follow up",
    "deliver ", "complete ", "schedule ", "prepare ", "fix ", "deploy ", "ship "
)
URGENT_CUES = ("urgent", "asap", "immediately", "critical", "blocker", "p0")
HIGH_CUES = ("high priority", "important", "must", "p1", "launch", "deadline")
LOW_CUES = ("low priority", "nice to have", "when you have time", "p3")


def _extract_date(text: str) -> Optional[str]:
    match = DATE_PATTERN.search(text)
    return match.group(1).strip() if match else None


def _extract_subject(text: str) -> str:
    lowered = text.lower()
    if "launch" in lowered:
        return "Product Launch Date"
    if "pricing" in lowered or "price" in lowered:
        return "Pricing Strategy"
    if "budget" in lowered:
        return "Budget Allocation"
    if "vendor" in lowered or "provider" in lowered:
        return "Vendor Selection"
    if "roadmap" in lowered or "release" in lowered:
        return "Release Roadmap"
    if "security" in lowered or "compliance" in lowered:
        return "Security & Compliance"
    # Fallback: first 6 meaningful words
    cleaned = re.sub(r"[^A-Za-z0-9\s-]", "", text).strip()
    words = cleaned.split()[:6]
    return " ".join(words).title() if words else "General Decision"


def _infer_priority(text: str) -> str:
    lowered = text.lower()
    if any(cue in lowered for cue in URGENT_CUES):
        return "URGENT"
    if any(cue in lowered for cue in HIGH_CUES):
        return "HIGH"
    if any(cue in lowered for cue in LOW_CUES):
        return "LOW"
    return "MEDIUM"


def _extract_owner(text: str, speaker_label: str, known_participants: List[str]) -> Optional[str]:
    lowered = text.lower()
    # Explicit "I will / I'll" -> speaker is the owner (unless Unknown Speaker)
    if re.search(r"\b(i will|i'll|i can take|i'm taking)\b", lowered):
        return None if speaker_label == "Unknown Speaker" else speaker_label

    # Explicit "assigned to Name" or "Name will ..." or "Name needs to ..."
    for person in known_participants:
        if person == "Unknown Speaker":
            continue
        first_name = person.split()[0]
        pattern = re.compile(
            rf"\b(?:{re.escape(person)}|{re.escape(first_name)})\s+(?:will|to|needs to|should|is responsible|owns)\b"
            rf"|\bassigned to\s+(?:{re.escape(person)}|{re.escape(first_name)})\b",
            re.IGNORECASE,
        )
        if pattern.search(text):
            return person

    # Pattern for capitalized single name followed by "will" / "needs to"
    m = re.search(r"\b([A-Z][a-z]{2,18})\s+(?:will|needs to|is going to|should)\b", text)
    if m and m.group(1) not in {"We", "They", "This", "That", "There", "Team", "Someone", "Everyone"}:
        return m.group(1)

    return None  # Never invent an owner


class MeetingExtractionAgent:
    """
    Agents 2, 3, and 4:
    - Meeting Understanding (summary, topics, participants)
    - Decision Intelligence (CONFIRMED vs PROPOSED vs REJECTED vs UNRESOLVED)
    - Task Intelligence (action items, owners, deadlines, priorities, dependencies)
    Enforces strict Pydantic validation and flags uncertain items for human review.
    """

    def __init__(self) -> None:
        self.last_usage: Dict[str, Any] = {
            "provider": "deterministic",
            "input_tokens": None,
            "output_tokens": None,
        }

    def extract(
        self,
        meeting_title: str,
        segments: List[Dict[str, Any]],
        known_participants: Optional[List[str]] = None,
    ) -> MeetingUnderstandingOutput:
        if settings.AI_PROVIDER in {"openai", "gemini"}:
            output, self.last_usage = extract_with_provider(
                provider=settings.AI_PROVIDER,
                meeting_title=meeting_title,
                segments=segments,
                known_participants=known_participants,
            )
            return output
        if settings.AI_PROVIDER not in {"deterministic", "demo", "local_demo"}:
            raise RuntimeError(f"Unsupported AI_PROVIDER '{settings.AI_PROVIDER}'.")
        self.last_usage = {"provider": "deterministic", "input_tokens": None, "output_tokens": None}

        participants_set = set(known_participants or [])
        for seg in segments:
            label = seg.get("speaker_label", "")
            if label and label != "Unknown Speaker":
                participants_set.add(label)
        participants = sorted(participants_set)

        decisions: List[ExtractedDecision] = []
        action_items: List[ExtractedActionItem] = []
        topics_set = set()

        for seg in segments:
            idx = int(seg["segment_index"])
            speaker = seg.get("speaker_label", "Unknown Speaker")
            text = seg.get("text", "").strip()
            lowered = text.lower()
            if not text:
                continue

            extracted_date = _extract_date(text)

            # 1. Decision Intelligence (Agent 3)
            decision_type: Optional[str] = None
            confidence = 0.88
            needs_review = False

            if any(cue in lowered for cue in REJECTED_CUES):
                decision_type = "REJECTED"
                confidence = 0.87
            elif any(cue in lowered for cue in PROPOSED_CUES):
                decision_type = "PROPOSED"
                confidence = 0.82
                needs_review = True
            elif any(cue in lowered for cue in CONFIRMED_CUES):
                decision_type = "CONFIRMED"
                confidence = 0.92
                needs_review = speaker == "Unknown Speaker"

            if decision_type:
                subject = _extract_subject(text)
                topics_set.add(subject)
                decisions.append(
                    ExtractedDecision(
                        subject=subject,
                        statement=text,
                        decision_type=decision_type,
                        key_value=extracted_date,
                        evidence_quote=text,
                        source_segment_index=idx,
                        participants=[speaker] if speaker != "Unknown Speaker" else [],
                        confidence=confidence,
                        needs_review=needs_review,
                    )
                )

            # 2. Task Intelligence (Agent 4)
            if any(cue in lowered for cue in ACTION_CUES):
                owner = _extract_owner(text, speaker, participants)
                priority = _infer_priority(text)
                deps: List[str] = []
                dep_match = re.search(r"(?:after|depends on|blocked by)\s+([^.;]+)", text, re.IGNORECASE)
                if dep_match:
                    deps.append(dep_match.group(1).strip())

                # Uncertain if owner or deadline is missing -> flag for human review
                task_needs_review = (owner is None) or (extracted_date is None)
                task_confidence = 0.91 if not task_needs_review else 0.74
                title = text[:110].rstrip(".")
                if len(text) > 110:
                    title = title.rsplit(" ", 1)[0] + "..."

                action_items.append(
                    ExtractedActionItem(
                        title=title,
                        description=text,
                        assigned_name=owner,
                        deadline=extracted_date,
                        priority=priority,
                        dependencies=deps,
                        evidence_quote=text,
                        source_segment_index=idx,
                        confidence=task_confidence,
                        needs_review=task_needs_review,
                    )
                )

        if not topics_set:
            topics_set.add(meeting_title)

        summary = (
            f"Processed '{meeting_title}' with {len(segments)} transcript segment(s), "
            f"identifying {len(decisions)} decision item(s) and {len(action_items)} action item(s)."
        )

        # Strict Pydantic validation
        return MeetingUnderstandingOutput(
            summary=summary,
            topics=sorted(topics_set),
            participants=participants,
            decisions=decisions,
            action_items=action_items,
        )
