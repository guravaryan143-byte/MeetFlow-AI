# MeetFlow AI

MeetFlow AI turns meeting conversations into traceable decisions, action items, cross-meeting conflict reviews, and approval-gated external actions.

## The problem

Meeting outcomes are easy to lose across recordings, notes, and follow-up tools. Teams can miss changed commitments, leave ownership unclear, or act on an unreviewed suggestion.

## The solution

MeetFlow processes transcripts into structured decisions and tasks, keeps evidence linked to its meeting, compares new commitments with organizational history, and routes supported external actions through an explicit human approval gate.

The local demo uses deterministic, rule-based processing and mocked integrations. It is not a live language model or a live external provider.

## Features

- Register and sign in to an isolated workspace.
- Create meetings and upload transcript or supported audio files.
- Process transcripts into decisions and action items; correct transcript speaker attribution.
- Review cross-meeting conflicts with evidence and preserved decision history.
- Manage tasks, reminders, weekly digests, and approval requests.
- Use optional OpenAI or Gemini extraction and OpenAI Whisper transcription when configured.
- Prepare Linear, Trello, email, and Google Calendar actions; execution requires an authorized approval. Slack is mock-only.
- View workspace analytics and audit history.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system details and [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) for the API surface.

## Architecture and technology

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Zustand, and Recharts.
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy, and Alembic.
- **Persistence:** SQLite for local/test runs; PostgreSQL with pgvector in Docker Compose.
- **Testing:** unittest, Vitest, TypeScript checks, and Playwright.
- **Deployment configuration:** Docker Compose and a Render service template.

The backend uses organization-scoped routes and role-based authorization. Provider credentials remain server-side. External actions are executed only through `AuthorizedExecutionService` after approval.

## Repository layout

```text
backend/
  app/                 FastAPI routes, agents, integrations, persistence
  alembic/             Database migration configuration and versions
  tests/               Backend tests
  Dockerfile
frontend/
  src/                 React application
  tests/               Unit and end-to-end tests
  Dockerfile
docs/                  Architecture, API, development, and test documentation
scripts/               Local project utilities
docker-compose.yml
.env.example           Safe local configuration template
```

## Prerequisites

- Git.
- Docker Desktop with the Docker Compose plugin (recommended).
- For running services without Docker: Python 3.11+ and Node.js 22.12+.

## Local setup with Docker

```bash
git clone YOUR_REPOSITORY_URL
cd MeetFlow-AI
cp .env.example .env
docker compose up --build -d
docker compose ps
```

In PowerShell, use `Copy-Item .env.example .env` instead of `cp`. The Compose stack starts PostgreSQL/pgvector, FastAPI, and the frontend. It applies the Alembic migration during backend container startup.

Local URLs:

- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend health: [http://localhost:8000/health](http://localhost:8000/health)
- Swagger API documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

To stop the services while retaining database and uploaded data, run `docker compose down`. Do not use `docker compose down -v` unless you intentionally want to delete the persistent volumes.

## Environment and provider configuration

`.env.example` contains local-development placeholders. Copy it to `.env` for local use; `.env` is ignored by Git. Replace the development database password and JWT secret before exposing services beyond localhost. Production requires `ENVIRONMENT=production`, a strong unique `JWT_SECRET_KEY`, TLS, explicit CORS origins, and a managed database.

AI and transcription calls are opt-in:

| Capability | Configuration |
|---|---|
| OpenAI extraction | `AI_PROVIDER=openai`, `OPENAI_API_KEY`; optional `OPENAI_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_MAX_RETRIES` |
| Gemini extraction | `AI_PROVIDER=gemini`, `GEMINI_API_KEY`; optional `GEMINI_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_MAX_RETRIES` |
| OpenAI Whisper transcription | `TRANSCRIPTION_PROVIDER=openai` and `WHISPER_API_KEY` or `OPENAI_API_KEY`; optional `OPENAI_TRANSCRIPTION_MODEL` |
| Local deterministic demo | `AI_PROVIDER=deterministic`, `TRANSCRIPTION_PROVIDER=deterministic` |

Deterministic processing is rule-based and does not fabricate a live AI result. Audio processing requires a configured transcription provider; provider failures are reported. Do not put credentials in `VITE_*` variables or commit them.

## External integrations

Set `INTEGRATION_MODE=live` and configure credentials in the backend environment to use live adapters. In the default `mock` mode, actions are simulated.

| Provider | Required configuration / notes |
|---|---|
| Linear | `LINEAR_API_KEY`, `LINEAR_TEAM_ID`; assignments need an explicit provider user-ID mapping. |
| Trello | `TRELLO_API_KEY`, `TRELLO_TOKEN`, `TRELLO_LIST_ID`; assignments need an explicit member mapping. |
| Email | `SMTP_HOST`, `SMTP_FROM_EMAIL`; normally also SMTP port, username, password, and TLS settings. |
| Google Calendar | `GOOGLE_CALENDAR_ACCESS_TOKEN`, optionally `GOOGLE_CALENDAR_ID`. OAuth consent and token refresh are not implemented. |
| Slack | Mock-only; live delivery is not implemented. |

Integration adapters have mock-based tests only; no real provider account or paid API call was used for verification. A suggested action is not executed until an authorized user approves it and explicitly requests execution. Use a test provider account before enabling live actions.

## Run without Docker

Copy `.env.example` to `.env`, then install the backend dependencies and start FastAPI:

```powershell
Set-Location backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000 --env-file ..\.env
```

In a second terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

The standalone backend uses SQLite when `DATABASE_URL` is unset. `DATABASE_URL=sqlite:///./meetflow.db` is a local-only option. Docker Compose configures PostgreSQL.

## Tests

Run the backend tests:

```powershell
Set-Location backend
python -m unittest discover -s tests -v
```

Run the frontend checks:

```powershell
Set-Location frontend
npm ci
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Playwright starts an isolated backend and frontend on ports 8001 and 5174 with a temporary SQLite database and uploads directory. It does not clear or use the Compose PostgreSQL volume. See [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for the latest recorded results and limitations.

## Demonstration workflow

1. Register a demo workspace and open **Meetings**.
2. Upload or ingest a transcript confirming a decision and assigning a task.
3. Process another meeting that proposes a changed commitment.
4. Review the historical and new evidence in **Conflict Review**; resolve the conflict without discarding history.
5. Review the resulting task and prepare an external action.
6. In **Approval Inbox**, reject or approve the action. Execute only an explicitly approved action. In mock mode, execution is simulated.

Use synthetic meeting data and a dedicated test workspace; do not use private meeting transcripts for a public demonstration.

## Security considerations

- Never commit `.env`, credentials, private keys, local databases, uploads, or generated test artifacts.
- Passwords are hashed; JWTs are validated and expire.
- Authorization and organization scoping are enforced by the API.
- Approval is required for external side effects; edits invalidate prior approval and execution uses idempotency protection.
- Keep provider credentials in a deployment secret manager. Review CORS, TLS, backups, logs, rate limits, and OAuth token lifecycle before production use.
- Local development defaults are not production secrets or production configuration.

## Current limitations and future work

- Live provider accounts have not been used in testing; integrations are mock-tested.
- Google Calendar OAuth authorization and token refresh are not implemented.
- Slack has no live adapter.
- Production deployment, managed database operations, backups, and credential rotation must be configured for the chosen hosting environment.
- Future improvements may include completed OAuth lifecycle support, live-provider contract tests, and deployment-specific operational monitoring.

## Contributions

Please open an issue to describe a bug or proposed change, then submit a focused pull request with relevant tests and documentation. Do not include real credentials, personal transcripts, database files, or generated artifacts in issues or pull requests.

## License

There is currently no license file in this repository. No permission to reuse, modify, or redistribute the project is granted by this README; select and add a license before publishing under an open-source license.
