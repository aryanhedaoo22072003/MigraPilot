# Next implementation prompt — Phase 2 (Cursor / Codex / Claude Code)

Read `docs/original-build-spec.md`, `README.md`, and existing repository files first. This is the existing MigraPilot Phase 1 starter, NOT a greenfield app.

Implement **Phase 2: secure Informatica PowerCenter XML upload, parser, and SQL lineage storage**. Preserve existing authentication, project ownership, DB schema, React pages and API contracts. Do not use mock data or pretend parser failures are successes.

Specific requirements:
1. `POST /api/v1/projects/{id}/uploads`: authenticated engineer/admin + owner; XML and bulk ZIP; enforce body/file count/extracted-size limits, reject XML DTD/entities via `defusedxml`; defend against ZIP traversal, decompression bombs and parser abuse.
2. Persist `uploads`, `mappings`, `transformations`, `ports`, and `lineage_edges`, preserving `project_id` ownership checks on every nested fetch.
3. Handle PowerCenter `POWERMART/REPOSITORY/FOLDER/MAPPING`, `TRANSFORMATION`, `TRANSFORMFIELD`, `INSTANCE`, `CONNECTOR`, and `SOURCE`/`TARGET` where applicable; resolve transformation instances/fields and references. Don't assume every XML export is identical; provide explicit unsupported-construct diagnostics.
4. Run parsing in Celery, persist job status/progress/errors, expose `GET /api/v1/jobs/{id}` (and SSE if practical). Validate uploads before enqueuing.
5. Implement `GET /api/v1/projects/{id}/mappings` and `GET /api/v1/mappings/{id}`; return transformation/port/edge data for the next React Flow phase.
6. Add actual upload UI and mapping list to project workspace with loading/error state, retry and progress indicators. Only mark `parsed` after successfully persisting a mapping.
7. Supply 3 non-sensitive, realistic PowerCenter XML fixtures and parser/API tests: Expression+Filter, Lookup+Aggregator, and tricky Oracle NULL expression. Explain semantic limitations.
8. Use Alembic for any SQL changes, Pydantic schemas and typed TypeScript client. Update README. Do not introduce MongoDB, do not switch frontend/backend frameworks, do not add unrelated features.

Acceptance: Docker Compose starts all services; API tests pass; actual XML upload extracts correct mappings, transformation ports and connector edges; the UI shows parsed mappings from PostgreSQL; malformed XML and inaccessible projects fail safely.
