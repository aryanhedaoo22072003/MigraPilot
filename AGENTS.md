# MigraPilot — instructions for Codex

## Product
MigraPilot is an AI-assisted legacy ETL migration copilot: **Convert it. Prove it. Fix it.** It parses Informatica PowerCenter XML, produces reviewed dbt/SQL, verifies migrated outputs with read-only shadow comparisons, and diagnoses mismatches with evidence.

## Read first
- `README.md` — actual implemented features and local setup
- `docs/original-build-spec.md` — full product specification
- `docs/CODEX-START-HERE.md` — immediate Phase 1 verification task
- `docs/NEXT-CURSOR-PROMPT.md` — Phase 2 implementation task after Phase 1 passes

## Fixed architecture
- Frontend: React 18, TypeScript, Vite, Tailwind, shadcn/ui (introduce as needed), React Flow (later), Monaco (later)
- Backend: Python FastAPI, SQLAlchemy async, Pydantic, Alembic
- SQL storage: PostgreSQL + pgvector; **never MongoDB**
- Queue: Celery + Redis
- AI: provider-agnostic adapter, current implementation points to Anthropic/Claude and requires separate API credentials. No AI calls in Phase 1.
- Local orchestration: Docker Compose
- API testing: Postman; collection `postman/MigraPilot-Phase1.postman_collection.json`, environment `postman/MigraPilot-Local.postman_environment.json`

## Working rules
1. **Never silently replace the stack or rebuild from zero**. Modify this repo incrementally.
2. Before new work, inspect existing code and run applicable tests. Explicitly report which checks you actually ran.
3. For new endpoints: SQL model/migration → FastAPI endpoint → automated tests → Postman collection → UI integration. Keep API contract documented.
4. Validate project ownership and role on every nested resource, not just the top-level project.
5. Database schema changes use an Alembic migration. Keep `db/schema.sql` in sync as a reference.
6. Never embed credentials or personal row data in prompts/logs; mask/redact externally sent data. Never execute unreviewed AI-generated SQL with write permissions.
7. Handle malformed XML, ZIP bombs, traversal and XML entity attacks when upload support is implemented. No invented migration results or fake verified metrics.
8. Keep UI polished but avoid hiding functional errors behind mock dashboards or placeholder success banners.
9. Prefer small, testable feature increments. Don't implement Phase 2 until Phase 1 has passed local integration checks.
