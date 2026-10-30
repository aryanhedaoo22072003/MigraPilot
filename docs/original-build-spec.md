# MigraPilot: Full-Stack Build Prompt

Copy everything below into your AI coding tool (Claude Code, Cursor, Lovable, Bolt, etc.).

---

## ROLE

You are a senior full-stack engineer and data engineering architect. Build **MigraPilot**, an AI-powered legacy ETL migration copilot. It converts legacy ETL jobs (Informatica PowerCenter XML) into modern dbt/SQL, proves the new pipeline produces identical data, and uses AI to diagnose exactly why any job fails or any numbers don't match.

## PRODUCT IDEA (one line)

"Convert it. Prove it. Fix it." Upload old mappings, get new code, verify the data matches, and get AI-explained root causes when it doesn't.

## TARGET USER

Data engineers and migration teams at enterprises moving off PowerCenter / ODI to dbt + a modern warehouse.

## TECH STACK

- **Frontend:** React 18 + TypeScript + Vite, Tailwind CSS, shadcn/ui, React Flow (lineage graph), Monaco Editor (code and diff view), Recharts (charts), TanStack Query, Zustand
- **Backend:** Python FastAPI (async), SQLAlchemy 2.0, Alembic migrations, Pydantic v2
- **Database:** PostgreSQL (all backend storage defined as SQL, schema below). Keep DDL portable so it can be adapted to SQL Server.
- **Queue / background jobs:** Celery + Redis (parsing, conversion, shadow runs)
- **AI layer:** Anthropic Claude API (structured JSON output, tool use). Wrap in a provider-agnostic `ai_service.py`.
- **Auth:** JWT (email + password), role-based (admin, engineer, viewer)
- **Dev setup:** Docker Compose (api, worker, db, redis, web), `.env.example`, seed data script

## CORE FEATURES

### 1. Project Workspace
- Create migration projects (name, source system, target system).
- Dashboard with progress ring: % converted, % verified, % failing.

### 2. Smart Upload and Parser
- Drag-and-drop PowerCenter XML (single or bulk ZIP).
- Parse mappings, sources, targets, transformations (Expression, Filter, Joiner, Lookup, Aggregator, Router, Sorter, Update Strategy), ports, and connectors.
- Store the parsed structure in SQL tables (see schema).

### 3. Interactive Lineage Graph
- React Flow canvas: source → transformations → target.
- Click a node to see port-level logic and the converted SQL for that step.
- Column-level lineage highlighting (click a target column to light up its upstream path).

### 4. AI Converter
- One click converts each mapping to a dbt model (`.sql` + `schema.yml`) using CTEs (one CTE per transformation, readable output).
- Per-mapping **Confidence Score (0-100)** with reasons.
- Flags risky constructs (Oracle-specific functions, implicit casts, NULL handling, date formats, sequence generators).
- Side-by-side Monaco view: original mapping logic (human-readable) vs generated SQL. User can edit and re-run AI with a comment ("use COALESCE here").

### 5. Shadow Run and Data Diff Engine
- Configure legacy output table and new output table connections.
- Compare: row counts, column checksums, null counts, min/max, distinct counts, and sampled row-level diffs on the primary key.
- Visual **Match Score** per table, with mismatched columns highlighted in red.
- Row-level diff viewer (legacy value vs new value).

### 6. AI Autopsy (signature feature)
- Triggered automatically on a failed job or a data mismatch, or manually by pasting a raw log.
- Inputs: error log or diff results + the mapping definition + the generated SQL.
- Output (structured): **Root cause**, **Evidence** (the exact transformation and column), **Suggested fix** (code patch), **Confidence**, **Similar past cases**.
- "Apply fix" button re-generates the model and queues a new shadow run.
- Autopsy timeline view showing each attempt, fix, and result.

### 7. Failure Knowledge Base (learning loop)
- Every resolved autopsy is stored (construct → symptom → fix).
- Future conversions consult this table (retrieval via pgvector embeddings) so the same mismatch is prevented.
- Show an "Avoided N known issues" badge on conversions.

### 8. Ask MigraPilot (chat)
- Chat panel scoped to the project: "Why does the HR_HEADCOUNT mapping differ by 12 rows?", "Which mappings are highest risk?", "Summarize what changed in the last run."
- Answers cite the mapping, run, and column they came from.

### 9. Migration Readiness Report
- Complexity heatmap of all mappings (green/amber/red).
- Estimated effort in days per mapping (AI-assisted).
- Export PDF/Markdown report: coverage, verified tables, open issues, risks.

### 10. Auto Documentation
- Generate plain-English business descriptions of every mapping and a data dictionary, exportable.

## UI / UX (make it attractive)
- Dark-first modern theme with a light toggle; accent gradient (indigo to cyan).
- Glassmorphism cards, subtle animations (Framer Motion), skeleton loaders.
- Animated **pipeline flow** on the dashboard (data "packets" moving from legacy to new).
- Status chips: Parsed, Converted, Verified, Failing.
- Command palette (Ctrl/Cmd+K) to jump to any mapping.
- Toasts for background job completion; live job progress via WebSocket/SSE.
- Fully responsive; empty states with illustrations and a "Load demo project" button.

## BACKEND DATABASE (SQL, PostgreSQL)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
  id            BIGSERIAL PRIMARY KEY,
  email         VARCHAR(255) UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role          VARCHAR(20) NOT NULL DEFAULT 'engineer'
                CHECK (role IN ('admin','engineer','viewer')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
  id            BIGSERIAL PRIMARY KEY,
  owner_id      BIGINT NOT NULL REFERENCES users(id),
  name          VARCHAR(200) NOT NULL,
  source_system VARCHAR(50) NOT NULL DEFAULT 'powercenter',
  target_system VARCHAR(50) NOT NULL DEFAULT 'dbt_postgres',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE uploads (
  id          BIGSERIAL PRIMARY KEY,
  project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  file_name   VARCHAR(255) NOT NULL,
  raw_xml     TEXT,
  status      VARCHAR(20) NOT NULL DEFAULT 'uploaded',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mappings (
  id              BIGSERIAL PRIMARY KEY,
  project_id      BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  upload_id       BIGINT REFERENCES uploads(id),
  name            VARCHAR(255) NOT NULL,
  description_ai  TEXT,
  complexity      SMALLINT,              -- 1..10
  status          VARCHAR(20) NOT NULL DEFAULT 'parsed'
                  CHECK (status IN ('parsed','converted','verified','failing')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE transformations (
  id           BIGSERIAL PRIMARY KEY,
  mapping_id   BIGINT NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
  name         VARCHAR(255) NOT NULL,
  type         VARCHAR(50) NOT NULL,     -- Expression, Filter, Joiner, Lookup...
  logic_json   JSONB NOT NULL,
  seq_order    INT NOT NULL
);

CREATE TABLE ports (
  id                BIGSERIAL PRIMARY KEY,
  transformation_id BIGINT NOT NULL REFERENCES transformations(id) ON DELETE CASCADE,
  name              VARCHAR(255) NOT NULL,
  datatype          VARCHAR(50),
  direction         VARCHAR(10) CHECK (direction IN ('IN','OUT','INOUT','VAR')),
  expression        TEXT
);

CREATE TABLE lineage_edges (
  id            BIGSERIAL PRIMARY KEY,
  mapping_id    BIGINT NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
  from_port_id  BIGINT NOT NULL REFERENCES ports(id),
  to_port_id    BIGINT NOT NULL REFERENCES ports(id)
);

CREATE TABLE conversions (
  id                BIGSERIAL PRIMARY KEY,
  mapping_id        BIGINT NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
  version           INT NOT NULL DEFAULT 1,
  generated_sql     TEXT NOT NULL,
  schema_yml        TEXT,
  confidence        SMALLINT,            -- 0..100
  risk_flags        JSONB,
  model_used        VARCHAR(100),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (mapping_id, version)
);

CREATE TABLE connections (
  id          BIGSERIAL PRIMARY KEY,
  project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  label       VARCHAR(100) NOT NULL,
  kind        VARCHAR(30) NOT NULL,      -- postgres, sqlserver, oracle
  config_enc  TEXT NOT NULL              -- encrypted JSON, never plaintext
);

CREATE TABLE shadow_runs (
  id               BIGSERIAL PRIMARY KEY,
  conversion_id    BIGINT NOT NULL REFERENCES conversions(id) ON DELETE CASCADE,
  legacy_table     VARCHAR(255) NOT NULL,
  new_table        VARCHAR(255) NOT NULL,
  pk_columns       TEXT[] NOT NULL,
  status           VARCHAR(20) NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued','running','passed','failed','error')),
  match_score      NUMERIC(5,2),
  started_at       TIMESTAMPTZ,
  finished_at      TIMESTAMPTZ
);

CREATE TABLE diff_results (
  id            BIGSERIAL PRIMARY KEY,
  shadow_run_id BIGINT NOT NULL REFERENCES shadow_runs(id) ON DELETE CASCADE,
  column_name   VARCHAR(255),
  metric        VARCHAR(50) NOT NULL,    -- row_count, checksum, null_count...
  legacy_value  TEXT,
  new_value     TEXT,
  is_match      BOOLEAN NOT NULL
);

CREATE TABLE row_diffs (
  id            BIGSERIAL PRIMARY KEY,
  shadow_run_id BIGINT NOT NULL REFERENCES shadow_runs(id) ON DELETE CASCADE,
  pk_value      TEXT NOT NULL,
  column_name   VARCHAR(255) NOT NULL,
  legacy_value  TEXT,
  new_value     TEXT
);

CREATE TABLE autopsies (
  id              BIGSERIAL PRIMARY KEY,
  mapping_id      BIGINT NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
  shadow_run_id   BIGINT REFERENCES shadow_runs(id),
  trigger_type    VARCHAR(20) NOT NULL CHECK (trigger_type IN ('auto','manual_log','mismatch')),
  raw_log         TEXT,
  root_cause      TEXT NOT NULL,
  evidence        JSONB,
  suggested_fix   TEXT,
  confidence      SMALLINT,
  status          VARCHAR(20) NOT NULL DEFAULT 'open'
                  CHECK (status IN ('open','fix_applied','resolved','dismissed')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE failure_knowledge (
  id            BIGSERIAL PRIMARY KEY,
  construct     VARCHAR(255) NOT NULL,   -- e.g. 'Oracle NVL on empty string'
  symptom       TEXT NOT NULL,
  fix_pattern   TEXT NOT NULL,
  times_seen    INT NOT NULL DEFAULT 1,
  embedding     vector(1536)
);

CREATE TABLE chat_messages (
  id          BIGSERIAL PRIMARY KEY,
  project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id     BIGINT NOT NULL REFERENCES users(id),
  role        VARCHAR(10) NOT NULL CHECK (role IN ('user','assistant')),
  content     TEXT NOT NULL,
  citations   JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
  id          BIGSERIAL PRIMARY KEY,
  project_id  BIGINT REFERENCES projects(id) ON DELETE CASCADE,
  type        VARCHAR(30) NOT NULL,      -- parse, convert, shadow_run, autopsy
  status      VARCHAR(20) NOT NULL DEFAULT 'queued',
  progress    SMALLINT DEFAULT 0,
  error       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mappings_project ON mappings(project_id);
CREATE INDEX idx_transformations_mapping ON transformations(mapping_id);
CREATE INDEX idx_conversions_mapping ON conversions(mapping_id);
CREATE INDEX idx_autopsies_mapping ON autopsies(mapping_id);
CREATE INDEX idx_failure_embedding ON failure_knowledge
  USING ivfflat (embedding vector_cosine_ops);
```

## API ENDPOINTS (REST, `/api/v1`)

- `POST /auth/register`, `POST /auth/login`
- `GET/POST /projects`, `GET /projects/{id}/dashboard`
- `POST /projects/{id}/uploads` (XML or ZIP) then background parse job
- `GET /projects/{id}/mappings`, `GET /mappings/{id}` (with transformations, ports, lineage)
- `POST /mappings/{id}/convert`, `POST /conversions/{id}/regenerate` (body: user comment)
- `POST /conversions/{id}/shadow-runs`, `GET /shadow-runs/{id}` (metrics + row diffs)
- `POST /mappings/{id}/autopsy` (body: optional raw log), `POST /autopsies/{id}/apply-fix`
- `POST /projects/{id}/chat`
- `GET /projects/{id}/report?format=pdf|md`
- `GET /jobs/{id}/stream` (SSE for live progress)

## AI IMPLEMENTATION RULES

- All AI calls return **validated structured JSON** (Pydantic schemas) and never free text parsed by regex.
- Conversion prompt must include: mapping JSON, target dialect, retrieved `failure_knowledge` entries, and a rule to emit one CTE per transformation.
- Autopsy prompt must include: error log or diff summary, mapping JSON, generated SQL; it must name the exact transformation and column, and say "insufficient evidence" instead of guessing.
- Never send real row data to the AI. Send only schema, aggregates, and masked samples (config flag `MASK_PII=true`).
- Log token usage per call in a table for cost visibility.

## SECURITY

- Encrypt connection configs (Fernet) and never log credentials.
- Read-only DB users for shadow-run comparisons.
- Rate-limit AI endpoints; validate and sandbox uploaded XML (defusedxml, size limits).

## DELIVERABLES

1. Full repo structure (`/web`, `/api`, `/worker`, `/db`), with Docker Compose that runs with one command.
2. Alembic migration generating the schema above, plus `seed.sql` with a demo project (3 sample PowerCenter mappings, including one that intentionally causes a NULL-handling mismatch to showcase the Autopsy).
3. Working end-to-end demo flow: upload, parse, convert, shadow run, mismatch, AI autopsy, apply fix, pass.
4. README with setup, architecture diagram (Mermaid), and a 2-minute demo script.

## BUILD ORDER

1. DB schema and auth, then project CRUD
2. XML parser and lineage storage
3. Lineage graph UI
4. AI converter and diff editor
5. Shadow run engine and match score UI
6. AI Autopsy and apply-fix loop
7. Knowledge base retrieval
8. Chat, report export, polish and animations

Start by confirming the folder structure, then build step 1 and proceed in order. Ask before making any decision that changes the stack.
