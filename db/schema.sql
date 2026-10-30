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

