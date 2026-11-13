-- Phase 1 canonical initial schema. PostgreSQL + pgvector.
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
  from_port_id  BIGINT NOT NULL REFERENCES ports(id) ON DELETE CASCADE,
  to_port_id    BIGINT NOT NULL REFERENCES ports(id) ON DELETE CASCADE
);

CREATE TABLE conversions (
  id                BIGSERIAL PRIMARY KEY,
  mapping_id        BIGINT NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
  version           INT NOT NULL DEFAULT 1,
  generated_sql     TEXT NOT NULL,
  schema_yml        TEXT,
  confidence        SMALLINT,            -- 0..100
  confidence_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
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
  project_id       BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  mapping_id       BIGINT NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
  conversion_id    BIGINT NOT NULL REFERENCES conversions(id) ON DELETE CASCADE,
  owner_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  fixture_id       VARCHAR(100) NOT NULL,
  status           VARCHAR(20) NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued','running','completed','failed')),
  comparison_result VARCHAR(10) CHECK (comparison_result IS NULL OR comparison_result IN ('PASS','FAIL')),
  reference_row_count INT, migrated_row_count INT, matched_rows INT,
  missing_rows INT, unexpected_rows INT, duplicate_key_mismatches INT,
  column_mismatches INT, null_mismatches INT, numeric_precision_differences INT,
  mismatch_samples JSONB NOT NULL DEFAULT '[]'::jsonb,
  execution_time_ms INT,
  error TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at       TIMESTAMPTZ,
  completed_at     TIMESTAMPTZ
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
  project_id      BIGINT REFERENCES projects(id) ON DELETE CASCADE,
  mapping_id      BIGINT NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
  shadow_run_id   BIGINT REFERENCES shadow_runs(id),
  conversion_id   BIGINT REFERENCES conversions(id) ON DELETE CASCADE,
  owner_id        BIGINT REFERENCES users(id) ON DELETE CASCADE,
  trigger_type    VARCHAR(20) CHECK (trigger_type IN ('auto','manual_log','mismatch')),
  raw_log         TEXT,
  root_cause      TEXT,
  diagnosis_category VARCHAR(50),
  diagnosis_json  JSONB,
  evidence        JSONB NOT NULL DEFAULT '[]'::jsonb,
  suggested_fix   TEXT,
  suggested_corrections JSONB NOT NULL DEFAULT '[]'::jsonb,
  suggested_sql   TEXT,
  confidence      SMALLINT,
  status          VARCHAR(20) NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','running','completed','failed','open','fix_applied','resolved','dismissed')),
  model_used      VARCHAR(100),
  input_tokens    INT NOT NULL DEFAULT 0,
  output_tokens   INT NOT NULL DEFAULT 0,
  provider_error  VARCHAR(100),
  celery_task_id  VARCHAR(50) UNIQUE,
  heartbeat_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 100),
  CHECK (status IN ('open','fix_applied','resolved','dismissed') OR
    (shadow_run_id IS NOT NULL AND project_id IS NOT NULL AND mapping_id IS NOT NULL AND conversion_id IS NOT NULL AND owner_id IS NOT NULL))
);

CREATE TABLE failure_knowledge (
  id            BIGSERIAL PRIMARY KEY,
  construct     VARCHAR(255) NOT NULL,   -- e.g. 'Oracle NVL on empty string'
  symptom       TEXT NOT NULL,
  fix_pattern   TEXT NOT NULL,
  times_seen    INT NOT NULL DEFAULT 1,
  embedding     vector(1536)
);

-- Phase 7A verified knowledge. The legacy failure_knowledge placeholder above is
-- retained for migration compatibility and is not used for publication.
CREATE TABLE knowledge_candidates (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  mapping_id BIGINT NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
  owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_autopsy_id BIGINT NOT NULL REFERENCES autopsies(id) ON DELETE RESTRICT,
  original_shadow_run_id BIGINT NOT NULL REFERENCES shadow_runs(id) ON DELETE RESTRICT,
  original_conversion_id BIGINT NOT NULL REFERENCES conversions(id) ON DELETE RESTRICT,
  corrected_conversion_id BIGINT REFERENCES conversions(id) ON DELETE RESTRICT,
  corrected_conversion_version INT,
  passing_shadow_run_id BIGINT REFERENCES shadow_runs(id) ON DELETE RESTRICT,
  diagnosis_category VARCHAR(50) NOT NULL,
  transformation_identifiers JSONB NOT NULL DEFAULT '[]'::jsonb,
  affected_columns JSONB NOT NULL DEFAULT '[]'::jsonb,
  signature_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  root_cause_summary TEXT NOT NULL,
  suggested_corrective_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
  verified_remediation_summary TEXT,
  fixture_id VARCHAR(100) NOT NULL,
  verification_outcome VARCHAR(30) CHECK (verification_outcome IS NULL OR verification_outcome='PASS'),
  verification_scope VARCHAR(300),
  verification_evidence JSONB,
  status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','verified','published','rejected','archived')),
  reviewer_id BIGINT REFERENCES users(id) ON DELETE RESTRICT,
  review_notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  verified_at TIMESTAMPTZ,
  approved_at TIMESTAMPTZ,
  published_at TIMESTAMPTZ,
  archived_at TIMESTAMPTZ,
  CONSTRAINT uq_knowledge_project_autopsy UNIQUE (project_id, source_autopsy_id)
);

CREATE TABLE knowledge_events (
  id BIGSERIAL PRIMARY KEY,
  candidate_id BIGINT NOT NULL REFERENCES knowledge_candidates(id) ON DELETE CASCADE,
  actor_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  event_type VARCHAR(30) NOT NULL,
  from_status VARCHAR(20),
  to_status VARCHAR(20) NOT NULL,
  notes TEXT,
  evidence_snapshot JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_project_status ON knowledge_candidates(project_id, status, created_at);
CREATE INDEX idx_knowledge_mapping ON knowledge_candidates(mapping_id);
CREATE INDEX idx_knowledge_category ON knowledge_candidates(project_id, diagnosis_category);
CREATE INDEX idx_knowledge_events_candidate ON knowledge_events(candidate_id, created_at);

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
  upload_id   BIGINT REFERENCES uploads(id) ON DELETE CASCADE,
  type        VARCHAR(30) NOT NULL,      -- parse, convert, shadow_run, autopsy
  status      VARCHAR(20) NOT NULL DEFAULT 'queued',
  progress    SMALLINT DEFAULT 0,
  error       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mappings_project ON mappings(project_id);
CREATE INDEX idx_jobs_upload ON jobs(upload_id);
CREATE INDEX idx_transformations_mapping ON transformations(mapping_id);
CREATE INDEX idx_conversions_mapping ON conversions(mapping_id);
CREATE INDEX idx_autopsies_mapping ON autopsies(mapping_id);
CREATE INDEX idx_autopsies_shadow_created ON autopsies(shadow_run_id, created_at);
CREATE UNIQUE INDEX uq_autopsies_active_shadow ON autopsies(shadow_run_id)
  WHERE status IN ('queued','running');
CREATE INDEX idx_failure_embedding ON failure_knowledge
  USING ivfflat (embedding vector_cosine_ops);

-- AI calls are recorded for transparent cost monitoring (extension to source schema).
CREATE TABLE ai_usage (
  id          BIGSERIAL PRIMARY KEY,
  project_id  BIGINT REFERENCES projects(id) ON DELETE SET NULL,
  provider    VARCHAR(50) NOT NULL,
  model_used  VARCHAR(100) NOT NULL,
  operation   VARCHAR(50) NOT NULL,
  input_tokens INT NOT NULL DEFAULT 0,
  output_tokens INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

