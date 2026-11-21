# MeetFlow AI — Project Handoff

This handoff reflects the current implementation. Older generated handoff material may describe an earlier SQLite-only, mock-only checkpoint; use the current code and linked documentation instead.

## Current status

- The application has a React/TypeScript frontend and a FastAPI backend.
- Local standalone backend runs can use SQLite; Docker Compose uses PostgreSQL/pgvector and applies the Alembic migration.
- The frontend and backend use organization-scoped records and authenticated, role-checked API routes.
- Transcript processing supports deterministic local demo behavior and optional OpenAI/Gemini extraction and OpenAI Whisper transcription.
- Linear, Trello, email, and Google Calendar adapters support mock and opt-in live modes. Slack remains mock-only. No live provider account has been used for verification.
- External side effects require an authorized approval and explicit execution through `AuthorizedExecutionService`.
- No cloud deployment or public GitHub publication is implied by these local verification results.

## Local setup

1. Copy `.env.example` to `.env`; keep `.env` and credentials local.
2. Run `docker compose up --build -d`.
3. Check `docker compose ps`.
4. Open the frontend at `http://localhost:5173`, backend at `http://localhost:8000`, and Swagger at `http://localhost:8000/docs`.

Use synthetic data for demonstrations. `docker compose down` preserves the named database volume; do not use `docker compose down -v` unless its data should be deleted.

## Verification

Run backend tests from `backend/`:

```powershell
python -m unittest discover -s tests -v
```

Run frontend checks from `frontend/`:

```powershell
npm run lint
npm test
npm run build
npm run test:e2e
```

The current recorded results and test boundaries are in [TEST_REPORT.md](TEST_REPORT.md). Provider tests are mocked; no production, paid-provider, or live integration test was performed.

## Security and operations

- Do not publish `.env`, local databases, uploads, private keys, generated reports, or real meeting transcripts.
- Production requires a strong unique JWT secret, managed database, TLS, restricted CORS, secret storage, and an operational backup policy.
- Configure and validate live provider credentials in a non-production account before enabling external actions.
- Google Calendar OAuth consent and refresh are not implemented; Slack live delivery is not implemented.

For detailed architecture, API routes, and configuration, see [ARCHITECTURE.md](ARCHITECTURE.md), [API_DOCUMENTATION.md](API_DOCUMENTATION.md), and the root [README](../README.md).
