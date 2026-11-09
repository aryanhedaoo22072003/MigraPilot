from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.core.config import settings
from app.main import app
from app.models import Base, Conversion, ShadowRun
from app.routers import shadow_runs as router_module
from app.services.shadow_compare import compare_rows
from app.services.shadow_execution import ShadowTimeout, UnsafeShadowSQL, compile_shadow_sql, execute_shadow_sql
from app.services.shadow_fixtures import ORDERS_DISCOUNT_V1

FIXTURE_XML = Path(__file__).parent / "fixtures" / "expression_filter.xml"
GOOD_SQL = """with src as (select order_id, amount from {{ source('raw', 'src_orders') }}), final as (select order_id, amount * .90 as net_amount from src where amount * .90 > 0) select * from final"""


def test_comparison_detects_values_missing_extra_nulls_duplicates_and_tolerance():
    reference = [{"order_id": 1, "net_amount": Decimal("9.000")}, {"order_id": 2, "net_amount": None}]
    close = compare_rows(reference, [{"order_id": 1, "net_amount": Decimal("9.00001")}, {"order_id": 2, "net_amount": None}], ("order_id",), Decimal(".001"), 10)
    assert close["comparison_result"] == "PASS" and close["matched_rows"] == 2
    wrong = compare_rows(reference, [{"order_id": 1, "net_amount": Decimal("8.9")}, {"order_id": 2, "net_amount": 0}, {"order_id": 3, "net_amount": 1}], ("order_id",), Decimal(".001"), 10)
    assert wrong["comparison_result"] == "FAIL"
    assert wrong["column_mismatches"] == 2 and wrong["null_mismatches"] == 1
    assert wrong["numeric_precision_differences"] == 1 and wrong["unexpected_rows"] == 1
    missing = compare_rows(reference, [], ("order_id",), Decimal("0"), 1)
    assert missing["missing_rows"] == 2 and len(missing["mismatch_samples"]) == 1
    duplicate = compare_rows(reference, [{"order_id": 1, "net_amount": 9}, {"order_id": 1, "net_amount": 9}], ("order_id",), Decimal("0"), 10)
    assert duplicate["duplicate_key_mismatches"] == 1


def test_sql_compilation_is_narrow_and_ast_validated():
    compiled = compile_shadow_sql(GOOD_SQL, "run_12")
    assert '"run_12"."src_orders"' in compiled and "{{" not in compiled
    for unsafe in (
        "select * from {{ source('raw', 'src_orders') }}; delete from x",
        "select * from users",
        "select pg_sleep(10) from {{ source('raw', 'src_orders') }}",
        "select * from {{ ref('anything') }}",
    ):
        with pytest.raises(UnsafeShadowSQL): compile_shadow_sql(unsafe, "run_12")


@pytest.mark.asyncio
async def test_provider_query_timeout_is_classified_and_schema_is_cleaned(monkeypatch):
    import asyncpg
    from app.core.config import settings
    events = []
    class Transaction:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
    class Connection:
        def __init__(self, executor=False): self.executor = executor
        async def execute(self, sql, *args): events.append(sql)
        async def executemany(self, sql, rows): events.append("fixture_loaded")
        def transaction(self, **kwargs): return Transaction()
        async def fetch(self, sql): raise asyncpg.QueryCanceledError("timeout")
        async def close(self): events.append("closed")
    calls = 0
    async def connect(*args, **kwargs):
        nonlocal calls
        calls += 1
        return Connection(executor=calls == 2)
    monkeypatch.setattr(asyncpg, "connect", connect)
    monkeypatch.setattr(settings, "shadow_loader_url", "postgresql://loader")
    monkeypatch.setattr(settings, "shadow_executor_url", "postgresql://executor")
    with pytest.raises(ShadowTimeout): await execute_shadow_sql(77, GOOD_SQL, ORDERS_DISCOUNT_V1)
    assert any("DROP SCHEMA" in event for event in events)


@pytest.fixture
async def shadow_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    queued = []
    async def override_db():
        async with factory() as session: yield session
    original_delay = router_module.shadow_run_task.delay
    original_eager = settings.parse_tasks_eager
    settings.parse_tasks_eager = True
    router_module.shadow_run_task.delay = lambda run_id: queued.append(run_id)
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            registered = await client.post("/api/v1/auth/register", json={"email": "shadow@example.com", "password": "securepass123"})
            headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
            project = await client.post("/api/v1/projects", headers=headers, json={"name": "Shadow Project"})
            await client.post(f"/api/v1/projects/{project.json()['id']}/uploads", headers=headers, files={"file": ("mapping.xml", FIXTURE_XML.read_bytes(), "application/xml")})
            async with factory() as db:
                from app.models import Mapping
                mapping = (await db.execute(__import__('sqlalchemy').select(Mapping))).scalar_one()
                conversion = Conversion(mapping_id=mapping.id, version=1, generated_sql=GOOD_SQL, confidence_reasons=[], risk_flags=[])
                db.add(conversion); await db.commit(); await db.refresh(conversion)
                conversion_id = conversion.id
            yield client, factory, headers, conversion_id, queued
    finally:
        router_module.shadow_run_task.delay = original_delay
        settings.parse_tasks_eager = original_eager
        app.dependency_overrides.clear(); await engine.dispose()


@pytest.mark.asyncio
async def test_shadow_run_api_ownership_queue_and_persistence(shadow_api):
    client, factory, headers, conversion_id, queued = shadow_api
    created = await client.post(f"/api/v1/conversions/{conversion_id}/shadow-runs", headers=headers, json={"fixture_id": "orders_discount_v1"})
    assert created.status_code == 202 and created.json()["status"] == "queued"
    run_id = created.json()["id"]
    assert queued == [run_id]
    assert (await client.get(f"/api/v1/shadow-runs/{run_id}", headers=headers)).status_code == 200
    listed = await client.get(f"/api/v1/conversions/{conversion_id}/shadow-runs", headers=headers)
    assert listed.status_code == 200 and listed.json()[0]["id"] == run_id
    assert (await client.post(f"/api/v1/conversions/{conversion_id}/shadow-runs", headers=headers, json={"fixture_id": "unknown"})).status_code == 422
    assert (await client.get(f"/api/v1/shadow-runs/{run_id}")).status_code == 401
    other = await client.post("/api/v1/auth/register", json={"email": "other-shadow@example.com", "password": "securepass123"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert (await client.get(f"/api/v1/shadow-runs/{run_id}", headers=other_headers)).status_code == 404
    assert (await client.post(f"/api/v1/conversions/{conversion_id}/shadow-runs", headers=other_headers, json={"fixture_id": "orders_discount_v1"})).status_code == 404
    async with factory() as db:
        assert (await db.get(ShadowRun, run_id)).fixture_id == "orders_discount_v1"


@pytest.mark.asyncio
async def test_queue_failure_is_persisted(shadow_api):
    client, factory, headers, conversion_id, _ = shadow_api
    router_module.shadow_run_task.delay = lambda _: (_ for _ in ()).throw(ConnectionError())
    response = await client.post(f"/api/v1/conversions/{conversion_id}/shadow-runs", headers=headers, json={"fixture_id": "orders_discount_v1"})
    assert response.status_code == 503
    async with factory() as db:
        run = (await db.execute(__import__('sqlalchemy').select(ShadowRun))).scalar_one()
        assert run.status == "failed" and run.error.startswith("queue_unavailable")
