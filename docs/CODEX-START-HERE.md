# First Codex task: verify and stabilize Phase 1

Paste the prompt below into the Codex panel after opening the **migrapilot-starter** folder in VS Code.

---

You are my senior full-stack developer for MigraPilot. This is an EXISTING codebase, not a greenfield project. Read `AGENTS.md`, `README.md`, `docs/original-build-spec.md`, and inspect `api/`, `web/`, and `docker-compose.yml` before editing anything.

**Goal for this task:** Make Phase 1 fully operational locally with real PostgreSQL and Postman-ready endpoints. Do not implement XML parsing or AI conversion yet.

Architecture is fixed: React 18 + TypeScript + Vite + Tailwind, Python FastAPI + Pydantic + async SQLAlchemy + Alembic, PostgreSQL/pgvector, Celery + Redis, Docker Compose. Use Postman for API verification, not mock-only frontend responses.

Work items, in order:
1. Inspect and sanity-check Docker Compose config, `.env.example`, PostgreSQL startup, Alembic migration, FastAPI routing, frontend API base URL, and CORS. Fix genuine issues only; preserve current working behavior. Never add real secrets to Git.
2. Run `docker compose up --build` (if Docker is available) and confirm database migrations and health `GET /api/v1/health`. If Docker is unavailable, say so explicitly and perform offline checks.
3. Run backend tests with `cd api && python -m pytest -q`; add meaningful tests for JWT rejection, validation, project ownership, and role restrictions. Verify using real PostgreSQL too, if Docker is available.
4. Run frontend typecheck/build `cd web && npm install && npm run build`, fixing any actual errors.
5. Inspect and importability-check `postman/MigraPilot-Phase1.postman_collection.json` and `postman/MigraPilot-Local.postman_environment.json`. The request flow is: health → register (save JWT) → login → me → create project (save project ID) → list/get/dashboard/rename → delete → deleted-project 404. Ensure actual backend responses match the assertions. Use Postman locally or Newman/HTTP requests when available; don't claim Postman UI was used if it wasn't.
6. Confirm the React landing/login/dashboard/project creation uses these REAL APIs, with useful error/loading states and correct project ownership.
7. Update `README.md` with exact working setup commands and any known limitations.

**Acceptance criteria:** A fresh checkout can start via Docker Compose; migrations run; frontend loads; register/login/project CRUD are usable; API tests and frontend build pass; Postman collection is ready to import. No imaginary data, no premature XML/AI features.

At completion provide: changed files, commands executed and their real outputs, API endpoint checklist, any remaining blockers, and what to run next. Then STOP and wait for my next task.

---

## Once Phase 1 passes
The next Codex prompt is already provided in `docs/NEXT-CURSOR-PROMPT.md` (Phase 2 PowerCenter XML parser). Do not paste it until Phase 1 is tested.
