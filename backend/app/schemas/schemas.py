from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# --- Auth ---
class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=8, max_length=128)
    organization_name: Optional[str] = Field(default=None, max_length=200)
    organization_id: Optional[str] = None
    role: str = Field(default="ADMIN")
    timezone: str = Field(default="UTC")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        role = v.upper()
        if role not in {"ADMIN", "MANAGER", "MEMBER"}:
            raise ValueError("Role must be ADMIN, MANAGER, or MEMBER")
        return role


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]
    organization: Dict[str, Any]
    role: str


# --- Meetings & Transcripts ---
class MeetingCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    meeting_date: Optional[str] = None
    transcript_text: Optional[str] = None
    participants: List[str] = Field(default_factory=list)


class SegmentUpdateRequest(BaseModel):
    speaker_label: Optional[str] = None
    mapped_user_id: Optional[str] = None
    text: Optional[str] = None


# --- AI Structured Extraction Schemas (Strict Pydantic Validation) ---
class ExtractedDecision(BaseModel):
    subject: str = Field(..., min_length=2, max_length=300)
    statement: str = Field(..., min_length=5)
    decision_type: str = Field(..., pattern="^(CONFIRMED|PROPOSED|REJECTED|SUPERSEDED|UNRESOLVED)$")
    key_value: Optional[str] = None
    evidence_quote: str = Field(..., min_length=3)
    source_segment_index: int = Field(..., ge=0)
    participants: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    needs_review: bool = False


class ExtractedActionItem(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    description: Optional[str] = None
    assigned_name: Optional[str] = None  # Never invented; None if unknown
    deadline: Optional[str] = None       # Never invented; None if unknown
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    dependencies: List[str] = Field(default_factory=list)
    evidence_quote: str = Field(..., min_length=3)
    source_segment_index: int = Field(..., ge=0)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    needs_review: bool = False


class MeetingUnderstandingOutput(BaseModel):
    summary: str
    topics: List[str] = Field(default_factory=list)
    participants: List[str] = Field(default_factory=list)
    decisions: List[ExtractedDecision] = Field(default_factory=list)
    action_items: List[ExtractedActionItem] = Field(default_factory=list)


# --- Decisions ---
class DecisionConfirmRequest(BaseModel):
    conflict_id: Optional[str] = None
    resolution_action: str = Field(default="CONFIRM", pattern="^(CONFIRM|ADOPT_NEW|KEEP_EXISTING|REJECT)$")
    change_reason: Optional[str] = None


# --- Tasks ---
class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=300)
    description: Optional[str] = None
    meeting_id: Optional[str] = None
    assigned_user_id: Optional[str] = None
    assigned_name: Optional[str] = None
    deadline: Optional[str] = None
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    dependencies: List[str] = Field(default_factory=list)


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assigned_user_id: Optional[str] = None
    assigned_name: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = Field(default=None, pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    status: Optional[str] = Field(default=None, pattern="^(OPEN|IN_PROGRESS|COMPLETED|BLOCKED|CANCELLED)$")
    review_status: Optional[str] = Field(default=None, pattern="^(NEEDS_REVIEW|APPROVED|REJECTED)$")


class PrepareTaskSyncRequest(BaseModel):
    provider: str = Field(default="linear", pattern="^(linear|trello)$")
    action_type: str = Field(default="EXTERNAL_TASK_CREATE", pattern="^(EXTERNAL_TASK_CREATE|EXTERNAL_TASK_UPDATE)$")


# --- Memory ---
class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=5, ge=1, le=25)
    status_filter: Optional[str] = None


# --- Approvals ---
class ApprovalReviewRequest(BaseModel):
    comment: Optional[str] = None
    auto_execute: bool = False


class ApprovalEditRequest(BaseModel):
    proposed_content: Dict[str, Any]
    comment: Optional[str] = None


# --- Integrations ---
class IntegrationConnectRequest(BaseModel):
    workspace_name: str = Field(..., min_length=1, max_length=200)
    project_id: Optional[str] = None
    api_token: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)


# --- Reminders & Digests ---
class ReminderScheduleRequest(BaseModel):
    action_item_id: str
    scheduled_for: Optional[str] = None
    reminder_type: str = Field(default="UPCOMING", pattern="^(UPCOMING|OVERDUE|ESCALATION)$")
    timezone: str = Field(default="UTC")
    target_provider: str = Field(default="email", pattern="^(email|slack)$")


class DigestGenerateRequest(BaseModel):
    user_id: Optional[str] = None
    delivery_day: str = Field(default="Monday")
    delivery_time: str = Field(default="09:00")
    timezone: str = Field(default="UTC")
    digest_format: str = Field(default="markdown", pattern="^(markdown|html|json)$")
