import re
import time
from decimal import Decimal

import asyncpg
from sqlglot import exp, parse

from app.core.config import settings
from app.services.shadow_compare import compare_rows
from app.services.shadow_fixtures import ShadowFixture


class ShadowExecutionError(Exception):
    code = "execution_failed"


class UnsafeShadowSQL(ShadowExecutionError):
    code = "unsafe_sql"


class ShadowSandboxUnavailable(ShadowExecutionError):
    code = "sandbox_unavailable"


class ShadowTimeout(ShadowExecutionError):
    code = "execution_timeout"


SOURCE_PATTERN = re.compile(r"\{\{\s*source\(\s*(['\"])raw\1\s*,\s*(['\"])src_orders\2\s*\)\s*\}\}", re.I)
ALLOWED_FUNCTIONS = {"abs", "avg", "cast", "ceil", "ceiling", "coalesce", "count", "date_trunc", "floor", "greatest", "least", "lower", "max", "min", "nullif", "round", "sum", "trim", "try_cast", "upper"}
FORBIDDEN_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command, exp.Copy, exp.Merge, exp.Transaction)


def compile_shadow_sql(generated_sql: str, schema: str) -> str:
    if not re.fullmatch(r"run_[0-9]+", schema):
        raise UnsafeShadowSQL("Invalid isolated schema")
    matches = list(SOURCE_PATTERN.finditer(generated_sql))
    without_sources = SOURCE_PATTERN.sub("", generated_sql)
    if "{{" in without_sources or "{%" in without_sources or len(matches) != 1:
        raise UnsafeShadowSQL("Only the allowlisted raw.src_orders dbt source is supported")
    compiled = SOURCE_PATTERN.sub(f'"{schema}"."src_orders"', generated_sql)
    try:
        statements = parse(compiled, read="postgres")
    except Exception as exc:
        raise UnsafeShadowSQL("SQL could not be parsed") from exc
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeShadowSQL("Exactly one SQL statement is required")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)) or any(tree.find(node) for node in FORBIDDEN_NODES):
        raise UnsafeShadowSQL("Only a single read-only SELECT query is supported")
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name, database = table.name.lower(), table.db.lower()
        if name in ctes and not database:
            continue
        if name != "src_orders" or database != schema:
            raise UnsafeShadowSQL("Query references a non-allowlisted relation")
    for function in tree.find_all(exp.Func):
        function_name = (getattr(function, "name", "") or function.sql_name()).lower()
        if function_name not in ALLOWED_FUNCTIONS:
            raise UnsafeShadowSQL("Query uses a function outside the shadow allowlist")
    return compiled


async def execute_shadow_sql(run_id: int, generated_sql: str, fixture: ShadowFixture) -> tuple[list[dict], int]:
    if not settings.shadow_loader_url or not settings.shadow_executor_url:
        raise ShadowSandboxUnavailable("Shadow database is not configured")
    schema = f"run_{run_id}"
    compiled = compile_shadow_sql(generated_sql, schema)
    loader = executor = None
    started = time.monotonic()
    try:
        loader = await asyncpg.connect(settings.shadow_loader_url, timeout=5)
        await loader.execute(f'CREATE SCHEMA "{schema}"')
        await loader.execute(f'CREATE TABLE "{schema}"."src_orders" (order_id integer NOT NULL, amount numeric)')
        await loader.executemany(f'INSERT INTO "{schema}"."src_orders" (order_id, amount) VALUES ($1, $2)', [(row["order_id"], row["amount"]) for row in fixture.rows])
        await loader.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO shadow_executor')
        await loader.execute(f'GRANT SELECT ON "{schema}"."src_orders" TO shadow_executor')
        executor = await asyncpg.connect(settings.shadow_executor_url, timeout=5, server_settings={"application_name": "migrapilot_shadow"})
        async with executor.transaction(readonly=True):
            await executor.execute(f"SET LOCAL statement_timeout = '{settings.shadow_statement_timeout_ms}ms'")
            await executor.execute("SET LOCAL lock_timeout = '1000ms'")
            rows = await executor.fetch(f'SELECT * FROM ({compiled}) AS shadow_result LIMIT {settings.shadow_max_rows + 1}')
        if len(rows) > settings.shadow_max_rows:
            raise ShadowExecutionError("Shadow result exceeded the configured row limit")
        return [dict(row) for row in rows], int((time.monotonic() - started) * 1000)
    except (asyncpg.QueryCanceledError, TimeoutError) as exc:
        raise ShadowTimeout("Shadow query exceeded its time limit") from exc
    except (OSError, asyncpg.CannotConnectNowError, asyncpg.InvalidPasswordError) as exc:
        raise ShadowSandboxUnavailable("Shadow database is unavailable") from exc
    finally:
        if executor: await executor.close()
        if loader:
            try: await loader.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            finally: await loader.close()


async def execute_and_compare(run_id: int, generated_sql: str, fixture: ShadowFixture) -> dict:
    rows, elapsed = await execute_shadow_sql(run_id, generated_sql, fixture)
    result = compare_rows(list(fixture.expected), rows, fixture.business_keys, Decimal(settings.shadow_decimal_tolerance), settings.shadow_mismatch_sample_limit)
    result["execution_time_ms"] = elapsed
    return result
