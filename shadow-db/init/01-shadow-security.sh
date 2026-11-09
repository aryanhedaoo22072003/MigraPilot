#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=executor_password="$SHADOW_EXECUTOR_PASSWORD" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE shadow_migrapilot FROM PUBLIC;
CREATE ROLE shadow_executor LOGIN PASSWORD :'executor_password' CONNECTION LIMIT 2;
GRANT CONNECT ON DATABASE shadow_migrapilot TO shadow_executor;
ALTER ROLE shadow_executor SET default_transaction_read_only = on;
ALTER ROLE shadow_executor SET statement_timeout = '5s';
ALTER ROLE shadow_executor SET lock_timeout = '1s';
ALTER ROLE shadow_executor SET idle_in_transaction_session_timeout = '5s';
SQL
