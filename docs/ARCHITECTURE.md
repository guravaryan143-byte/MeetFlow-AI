# MeetFlow AI — System Architecture

## Runtime layers

1. **Presentation (`frontend/`)** — React, TypeScript, Vite, Tailwind, React Router, TanStack Query, Zustand, and Recharts. The dashboard reads API-backed data; transcript upload, conflict review, task management, approvals, and integration status are part of the existing UI.
2. **API (`backend/app/api/`)** — FastAPI routes use bearer JWT authentication, organization membership checks, and role-based authorization. Registration creates a new organization; self-service joining or assigning elevated roles is not supported.
3. **Agent pipeline (`backend/app/agents/`)** — Transcript validation/segmentation, extraction, semantic memory, cross-meeting conflict detection, approval preparation, reporting, and orchestration. `AI_PROVIDER=deterministic` is a local rule-based demo, not an LLM. Optional OpenAI/Gemini adapters validate structured output and evidence quotes; optional OpenAI Whisper transcription is configured independently. Provider failures are surfaced and do not produce fabricated results.
4. **Approval and execution (`backend/app/approvals/execution_service.py`)** — `AuthorizedExecutionService` checks action status, approval role, organization scope, payload hash, and idempotency before calling an integration adapter. An atomic state transition limits concurrent duplicate execution. AI suggestions only create pending work; they cannot invoke providers directly.
5. **Integrations (`backend/app/integrations/adapters.py`)** — Linear, Trello, SMTP email, and Google Calendar support mock mode and opt-in live adapters. Credentials are environment-only; provider calls are only reachable through the approval execution service. Live actions require each service's account-specific configuration. Slack is mock-only. Provider adapters have mocked tests; no live service credential has been verified.
6. **Persistence (`backend/app/db/`, `backend/alembic/`)** — The application supports local SQLite and PostgreSQL through a compatibility database layer. Docker Compose uses PostgreSQL/pgvector and applies Alembic migrations during backend startup; E2E tests use a unique temporary SQLite database. Decision versioning, organization-scoped records, approval/execution records, and audit logs are persisted.

## Cross-meeting decision flow

Meeting content is parsed into transcript segments with explicit unknown-speaker handling. Extraction stores confirmed, proposed, rejected, and unresolved items with evidence. Memory search compares the new candidate with organization-scoped historical decisions. Conflict detection emits a review record with evidence from each meeting; proposal-to-proposal pairs are not treated as confirmed contradictions. A human resolves the conflict, and decision versions preserve the historical record.

## Security boundaries

- Passwords are PBKDF2-hashed; JWTs are signature-validated and expire.
- Organization-scoped routes reject records outside the caller's organization.
- Registration does not accept caller-selected organizations or elevated roles.
- Upload extensions and content are validated, and file reads enforce a configured size limit.
- External credentials are never accepted as API connection payloads or returned by integration listing.
- Only an authorized approver can approve, reject, or execute an action.
- Changes after approval invalidate the approval hash; external execution is idempotency-keyed and audited.

## Configuration modes

- **Local demo:** `AI_PROVIDER=deterministic`, `TRANSCRIPTION_PROVIDER=deterministic`, `INTEGRATION_MODE=mock`; no paid calls.
- **Live AI:** select `openai` or `gemini` and provide its backend API key. Live Whisper requires `TRANSCRIPTION_PROVIDER=openai` and an OpenAI/Whisper key.
- **Live integrations:** set `INTEGRATION_MODE=live` and the provider credentials/config. Google Calendar currently accepts an externally acquired access token; OAuth consent and token refresh are not implemented.

See the root [README](../README.md) for environment variables and setup. See [TEST_REPORT.md](TEST_REPORT.md) for tested versus mocked behavior.
