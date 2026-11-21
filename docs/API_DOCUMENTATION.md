# MeetFlow AI — API Documentation

Interactive Swagger UI is served at `GET /docs`; ReDoc is at `GET /redoc`. Authenticated requests use `Authorization: Bearer <JWT>`. Routes are organization-scoped.

| Method | Endpoint | Auth / Role | Description |
|---|---|---|---|
| GET | `/health` | Public | Health check |
| POST | `/api/auth/register` | Public | Create a user and a new organization; organization joining and self-selected elevated roles are not supported |
| POST | `/api/auth/login` | Public | Authenticate and return a JWT |
| GET | `/api/auth/me` | Bearer JWT | Return current user, organization, and role |
| POST | `/api/meetings` | Bearer JWT | Create meeting with optional transcript text |
| POST | `/api/meetings/upload` | Bearer JWT | Upload supported audio/transcript file; configured maximum size is enforced |
| GET | `/api/meetings` | Bearer JWT | List organization meetings |
| GET | `/api/meetings/{id}` | Bearer JWT | Get meeting details and extracted records |
| POST | `/api/meetings/{id}/process` | Bearer JWT | Run the pipeline; provider configuration/failures are reported rather than replaced with fake output |
| GET | `/api/meetings/{id}/transcript` | Bearer JWT | Retrieve transcript, speakers, and segments |
| PATCH | `/api/transcripts/{id}/segments/{segment_id}` | Bearer JWT | Correct speaker identity or segment text |
| GET | `/api/decisions` | Bearer JWT | List organization decisions |
| GET | `/api/decisions/conflicts` | Bearer JWT | List open/resolved cross-meeting conflicts with evidence |
| GET | `/api/decisions/{id}` | Bearer JWT | Get decision history and related records |
| POST | `/api/decisions/{id}/confirm` | ADMIN / MANAGER | Confirm or resolve a decision while retaining historical versions |
| GET | `/api/tasks` | Bearer JWT | List organization tasks |
| POST | `/api/tasks` | Bearer JWT | Create an action item; linked meetings and assignees must belong to the caller's organization |
| PATCH | `/api/tasks/{id}` | Bearer JWT | Update an action item |
| DELETE | `/api/tasks/{id}` | Bearer JWT | Soft-delete an action item |
| POST | `/api/tasks/{id}/prepare-sync` | Bearer JWT | Create a pending external task-sync approval |
| POST | `/api/memory/search` | Bearer JWT | Search historical decisions in the caller's organization |
| GET | `/api/memory/history` | Bearer JWT | Chronological decision history |
| GET | `/api/approvals` | Bearer JWT | List approval records |
| GET | `/api/approvals/{id}` | Bearer JWT | Read one approval record |
| PATCH | `/api/approvals/{id}` | Bearer JWT | Edit proposed action content and invalidate any prior approval |
| POST | `/api/approvals/{id}/approve` | ADMIN / MANAGER | Approve a pending action |
| POST | `/api/approvals/{id}/reject` | ADMIN / MANAGER | Reject a pending or approved action |
| POST | `/api/approvals/{id}/execute` | ADMIN / MANAGER | Execute an approved action through `AuthorizedExecutionService` |
| GET | `/api/integrations` | Bearer JWT | List organization connections and current `mode` (`mock`/`live`) and `simulated` flag |
| POST | `/api/integrations/{provider}/connect` | ADMIN / MANAGER | Validate environment-configured provider credentials and store non-secret connection config; API tokens in request bodies are rejected |
| GET | `/api/notifications` | Bearer JWT | List notifications |
| GET | `/api/reminders` | Bearer JWT | List scheduled reminders |
| POST | `/api/reminders/schedule` | Bearer JWT | Schedule a deduplicated reminder as a pending approval |
| GET | `/api/digests` | Bearer JWT | List personalized weekly digests |
| POST | `/api/digests/generate` | Bearer JWT | Generate digest and queue delivery for approval |
| GET | `/api/analytics/overview` | Bearer JWT | Persisted workspace overview |
| GET | `/api/analytics/radar` | Bearer JWT | Commitment radar |
| GET | `/api/analytics/audit-logs` | Bearer JWT | Organization audit trail |

## Provider behavior

`AI_PROVIDER` is selected server-side (`deterministic`, `openai`, or `gemini`); `TRANSCRIPTION_PROVIDER` independently selects deterministic or OpenAI Whisper transcription. Missing credentials and provider errors fail explicitly. Upload size/extension validation is performed before processing.

`INTEGRATION_MODE=mock` is the safe default and reports simulated execution. `INTEGRATION_MODE=live` requires provider credentials configured in the backend environment. Provider-specific safe configuration, such as Linear team ID, Trello list ID, Google Calendar ID, and `user_id_map`, may be supplied in the connection config. Never send provider API keys through this endpoint.

All integration side effects require an explicit authorized approval and an `execute` request. Do not treat successful connection setup as approval or execution.
