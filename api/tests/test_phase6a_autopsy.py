import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from billiard.exceptions import SoftTimeLimitExceeded
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai_service import AIInvocation, AIProviderRequestError, AIService
from app.core.config import settings
from app.core.rate_limit import ai_autopsy_limiter
from app.database import get_db
from app.main import app
from app.models import AIUsage, Autopsy, Base, Conversion, Mapping, ShadowRun
from app.routers import autopsies as router_module
from app.schemas import AutopsyAIOutput
from app.services.autopsy import (
    AutopsyEvidenceError, build_autopsy_context, persist_autopsy_failure,
    process_autopsy, recover_stale_running_autopsies,
    validate_autopsy_references,
)
from app.worker import tasks as task_module

FIXTURE_XML = Path(__file__).parent / "fixtures" / "expression_filter.xml"
GOOD_SQL = "with src as (select order_id, amount from {{ source('raw', 'src_orders') }}), final as (select order_id, amount * .80 as net_amount from src) select * from final"


def diagnosis(**overrides):
    data = {
        "summary": "The calculated net amount differs from the expected output.",
        "diagnosis_category": "EXPRESSION_MISMATCH",
        "suspected_root_cause": "EXP_NET applies a different discount multiplier in generated SQL.",
        "observed_facts": ["The comparison reports column mismatches."],
        "hypotheses": ["The SQL multiplier does not preserve the PowerCenter expression."],
        "affected_transformations": ["EXP_NET"],
        "affected_columns": ["NET_AMOUNT"],
        "supporting_evidence": [
            {"reference": "metrics.column_mismatches", "observation": "One or more columns differ."},
            {"reference": "transformations.EXP_NET", "observation": "The expression transformation calculates NET_AMOUNT."},
        ],
        "confidence": 88,
        "confidence_reasons": ["The expression and mismatch metric point to the same output column."],
        "suggested_corrective_actions": ["Review the NET_AMOUNT multiplier against the PowerCenter expression."],
        "suggested_sql": "select order_id, amount * .90 as net_amount from source_data",
        "risks_and_limitations": ["The suggested SQL is unverified and must be shadow-tested."],
        "recommended_verification_steps": ["Create a new immutable conversion and rerun the fixture."],
        "more_evidence_required": False,
    }
    data.update(overrides)
    return data


class FakeProvider:
    def __init__(self, output=None, error=None):
        self.output = output or diagnosis()
        self.error = error
        self.payloads = []

    async def generate(self, system_prompt, payload, output_type):
        self.payloads.append(payload)
        assert "untrusted" in system_prompt
        if self.error:
            raise self.error
        return AIInvocation(
            result=output_type.model_validate(self.output), provider="mock",
            model_used="mock-gemini", input_tokens=222, output_tokens=111,
        )


@pytest.fixture
async def autopsy_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    queued = []

    async def override_db():
        async with factory() as session:
            yield session

    original_apply_async = router_module.autopsy_task.apply_async
    original_eager = settings.parse_tasks_eager
    original_limit = settings.ai_autopsy_rate_limit_per_minute
    settings.parse_tasks_eager = True
    settings.ai_autopsy_rate_limit_per_minute = 20
    ai_autopsy_limiter.reset()
    router_module.autopsy_task.apply_async = lambda args, task_id: queued.append(args[0])
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            owner = await client.post("/api/v1/auth/register", json={"email": "autopsy@example.com", "password": "securepass123"})
            owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
            project = await client.post("/api/v1/projects", headers=owner_headers, json={"name": "Autopsy Project"})
            await client.post(
                f"/api/v1/projects/{project.json()['id']}/uploads", headers=owner_headers,
                files={"file": ("mapping.xml", FIXTURE_XML.read_bytes(), "application/xml")},
            )
            other = await client.post("/api/v1/auth/register", json={"email": "other-autopsy@example.com", "password": "securepass123"})
            other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
            async with factory() as db:
                mapping = (await db.scalars(select(Mapping))).first()
                conversion = Conversion(
                    mapping_id=mapping.id, version=1, generated_sql=GOOD_SQL,
                    confidence_reasons=[], risk_flags=[], model_used="mock-converter",
                )
                db.add(conversion)
                await db.commit()
                await db.refresh(conversion)
                ids = (project.json()["id"], mapping.id, conversion.id, owner.json()["user"]["id"])
            yield client, factory, owner_headers, other_headers, ids, queued
    finally:
        router_module.autopsy_task.apply_async = original_apply_async
        settings.parse_tasks_eager = original_eager
        settings.ai_autopsy_rate_limit_per_minute = original_limit
        ai_autopsy_limiter.reset()
        app.dependency_overrides.clear()
        await engine.dispose()


async def add_run(factory, ids, status="completed", result="FAIL", error=None):
    project_id, mapping_id, conversion_id, owner_id = ids
    async with factory() as db:
        run = ShadowRun(
            project_id=project_id, mapping_id=mapping_id, conversion_id=conversion_id,
            owner_id=owner_id, fixture_id="orders_discount_v1", status=status,
            comparison_result=result, reference_row_count=3, migrated_row_count=3,
            matched_rows=0, missing_rows=0, unexpected_rows=0,
            duplicate_key_mismatches=0, column_mismatches=3, null_mismatches=0,
            numeric_precision_differences=3,
            mismatch_samples=[{"key": [1], "column": "NET_AMOUNT", "expected": "9.0", "actual": "8.0"}],
            error=error,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run.id


@pytest.mark.asyncio
async def test_fail_run_queues_enforces_auth_ownership_and_prevents_duplicates(autopsy_env):
    client, factory, owner, other, ids, queued = autopsy_env
    run_id = await add_run(factory, ids)
    assert (await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies")).status_code == 401
    assert (await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=other)).status_code == 404
    created = await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=owner)
    assert created.status_code == 202
    assert created.json()["status"] == "queued" and created.json()["shadow_run_id"] == run_id
    assert queued == [created.json()["id"]]
    duplicate = await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=owner)
    assert duplicate.status_code == 409
    assert (await client.get(f"/api/v1/autopsies/{created.json()['id']}", headers=owner)).status_code == 200
    assert (await client.get(f"/api/v1/autopsies/{created.json()['id']}", headers=other)).status_code == 404


@pytest.mark.asyncio
async def test_pass_and_processing_runs_are_rejected_but_sanitized_failure_is_eligible(autopsy_env):
    client, factory, owner, _, ids, _ = autopsy_env
    pass_id = await add_run(factory, ids, result="PASS")
    queued_id = await add_run(factory, ids, status="queued", result=None)
    failed_id = await add_run(factory, ids, status="failed", result=None, error="execution_timeout: private provider detail")
    unclassified_id = await add_run(factory, ids, status="failed", result=None, error="arbitrary unclassified text")
    passed = await client.post(f"/api/v1/shadow-runs/{pass_id}/autopsies", headers=owner)
    assert passed.status_code == 422 and "PASS" in passed.json()["detail"]
    assert (await client.post(f"/api/v1/shadow-runs/{queued_id}/autopsies", headers=owner)).status_code == 409
    assert (await client.post(f"/api/v1/shadow-runs/{failed_id}/autopsies", headers=owner)).status_code == 202
    assert (await client.post(f"/api/v1/shadow-runs/{unclassified_id}/autopsies", headers=owner)).status_code == 422


@pytest.mark.asyncio
async def test_task_persists_validated_diagnosis_tokens_history_without_mutating_conversion(autopsy_env):
    client, factory, owner, _, ids, _ = autopsy_env
    run_id = await add_run(factory, ids)
    first = (await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=owner)).json()
    provider = FakeProvider()
    async with factory() as db:
        before = (await db.get(Conversion, ids[2])).generated_sql
        await process_autopsy(db, first["id"], AIService(provider))
    report = (await client.get(f"/api/v1/autopsies/{first['id']}", headers=owner)).json()
    assert report["status"] == "completed" and report["diagnosis_category"] == "EXPRESSION_MISMATCH"
    assert report["confidence"] == 88 and report["model_used"] == "mock-gemini"
    assert (report["input_tokens"], report["output_tokens"]) == (222, 111)
    assert report["suggested_sql_verified"] is False
    payload = provider.payloads[0]
    assert payload["privacy"] == {"row_values_included": False, "credentials_included": False}
    assert "9.0" not in str(payload) and "8.0" not in str(payload)
    async with factory() as db:
        assert (await db.get(Conversion, ids[2])).generated_sql == before
        usage = (await db.scalars(select(AIUsage).where(AIUsage.operation == "autopsy"))).one()
        assert (usage.input_tokens, usage.output_tokens) == (222, 111)
        # Completed reports are historical; a later diagnosis is a new row.
    second = await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=owner)
    assert second.status_code == 202 and second.json()["id"] != first["id"]
    history = (await client.get(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=owner)).json()
    assert [item["id"] for item in history] == [second.json()["id"], first["id"]]


@pytest.mark.asyncio
async def test_failed_execution_context_is_sanitized(autopsy_env):
    _, factory, _, _, ids, _ = autopsy_env
    run_id = await add_run(factory, ids, status="failed", result=None, error="unsafe_sql: confidential table name")
    async with factory() as db:
        run = await db.get(ShadowRun, run_id)
        context, refs, _, _ = await build_autopsy_context(db, run)
    assert context["shadow_run"]["execution_error_category"] == "unsafe_sql"
    assert "confidential table name" not in str(context)
    assert "execution_error.category" in refs


@pytest.mark.asyncio
async def test_provider_failure_is_sanitized_and_does_not_create_usage(autopsy_env):
    client, factory, owner, _, ids, _ = autopsy_env
    run_id = await add_run(factory, ids)
    created = (await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=owner)).json()
    provider = FakeProvider(error=AIProviderRequestError("secret response"))
    async with factory() as db:
        await process_autopsy(db, created["id"], AIService(provider))
        record = await db.get(Autopsy, created["id"])
        assert record.status == "failed" and record.provider_error == "provider_request"
        assert not list(await db.scalars(select(AIUsage).where(AIUsage.operation == "autopsy")))


def test_local_schema_and_evidence_reference_validation_are_strict():
    with pytest.raises(ValidationError):
        AutopsyAIOutput.model_validate(diagnosis(diagnosis_category="NOT_REAL"))
    with pytest.raises(ValidationError):
        AutopsyAIOutput.model_validate(diagnosis(confidence=101))
    with pytest.raises(ValidationError):
        AutopsyAIOutput.model_validate(diagnosis(suggested_sql="drop table production"))
    output = AutopsyAIOutput.model_validate(diagnosis(
        affected_transformations=["INVENTED"],
        supporting_evidence=[{"reference": "metrics.invented", "observation": "Not supplied."}],
    ))
    with pytest.raises(AutopsyEvidenceError):
        validate_autopsy_references(
            output, {"metrics.column_mismatches"}, {"EXP_NET"}, {"NET_AMOUNT"},
        )


@pytest.mark.asyncio
async def test_invalid_structured_reference_fails_task_without_persistence(autopsy_env):
    client, factory, owner, _, ids, _ = autopsy_env
    run_id = await add_run(factory, ids)
    created = (await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=owner)).json()
    provider = FakeProvider(diagnosis(
        supporting_evidence=[{"reference": "columns.DOES_NOT_EXIST", "observation": "Invented evidence."}],
    ))
    async with factory() as db:
        await process_autopsy(db, created["id"], AIService(provider))
        record = await db.get(Autopsy, created["id"])
        assert record.status == "failed"
        assert record.provider_error == "invalid_structured_response"
        assert record.diagnosis_json is None


@pytest.mark.asyncio
async def test_queue_failure_is_sanitized_and_persisted(autopsy_env):
    client, factory, owner, _, ids, _ = autopsy_env
    run_id = await add_run(factory, ids)
    router_module.autopsy_task.apply_async = lambda *_, **__: (_ for _ in ()).throw(ConnectionError("private broker detail"))
    response = await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=owner)
    assert response.status_code == 503 and response.json()["detail"] == "AI Autopsy queue is unavailable"
    async with factory() as db:
        record = (await db.scalars(select(Autopsy))).one()
        assert record.status == "failed" and record.provider_error == "queue_unavailable"


@pytest.mark.asyncio
async def test_total_provider_budget_persists_terminal_timeout(autopsy_env, monkeypatch):
    client, factory, owner, _, ids, _ = autopsy_env
    run_id = await add_run(factory, ids)
    created = (await client.post(f"/api/v1/shadow-runs/{run_id}/autopsies", headers=owner)).json()

    class SlowProvider(FakeProvider):
        async def generate(self, system_prompt, payload, output_type):
            await asyncio.sleep(1)

    monkeypatch.setattr(settings, "ai_autopsy_request_budget_seconds", 0.01)
    async with factory() as db:
        await process_autopsy(db, created["id"], AIService(SlowProvider()))
    async with factory() as db:
        record = await db.get(Autopsy, created["id"])
        assert record.status == "failed"
        assert record.provider_error == "provider_timeout"
        assert record.completed_at is not None


@pytest.mark.asyncio
async def test_stale_recovery_protects_active_fresh_and_completed_records(autopsy_env):
    _, factory, _, _, ids, _ = autopsy_env
    run_id = await add_run(factory, ids)
    project_id, mapping_id, conversion_id, owner_id = ids
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    fresh = datetime.now(timezone.utc)
    async with factory() as db:
        rows = [
            Autopsy(id=101, shadow_run_id=run_id, project_id=project_id, mapping_id=mapping_id, conversion_id=conversion_id, owner_id=owner_id, status="running", celery_task_id="dead-task", started_at=old, heartbeat_at=old),
            Autopsy(id=102, shadow_run_id=run_id, project_id=project_id, mapping_id=mapping_id, conversion_id=conversion_id, owner_id=owner_id, status="running", celery_task_id="active-task", started_at=old, heartbeat_at=old),
            Autopsy(id=103, shadow_run_id=run_id, project_id=project_id, mapping_id=mapping_id, conversion_id=conversion_id, owner_id=owner_id, status="running", celery_task_id="fresh-task", started_at=fresh, heartbeat_at=fresh),
            Autopsy(id=104, shadow_run_id=run_id, project_id=project_id, mapping_id=mapping_id, conversion_id=conversion_id, owner_id=owner_id, status="completed", celery_task_id="complete-task", started_at=old, heartbeat_at=old, completed_at=old),
        ]
        db.add_all(rows)
        await db.commit()
        recovered = await recover_stale_running_autopsies(
            db, cutoff=fresh - timedelta(minutes=5), active_task_ids={"active-task"},
            active_autopsy_ids=set(), category="worker_interrupted_stale",
        )
        assert recovered == [101]
    async with factory() as db:
        stale, active, current, completed = [await db.get(Autopsy, key) for key in (101, 102, 103, 104)]
        assert stale.status == "failed" and stale.provider_error == "worker_interrupted_stale" and stale.completed_at
        assert active.status == "running"
        assert current.status == "running"
        assert completed.status == "completed" and completed.provider_error is None


@pytest.mark.asyncio
async def test_terminal_failure_update_is_conditional_and_preserves_completed(autopsy_env):
    _, factory, _, _, ids, _ = autopsy_env
    run_id = await add_run(factory, ids)
    project_id, mapping_id, conversion_id, owner_id = ids
    async with factory() as db:
        completed = Autopsy(
            shadow_run_id=run_id, project_id=project_id, mapping_id=mapping_id,
            conversion_id=conversion_id, owner_id=owner_id, status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(completed)
        await db.commit()
        await db.refresh(completed)
        completed_id = completed.id
        assert not await persist_autopsy_failure(db, completed_id, "task_soft_timeout")
    async with factory() as db:
        preserved = await db.get(Autopsy, completed_id)
        assert preserved.status == "completed" and preserved.provider_error is None


def test_soft_time_limit_boundary_records_sanitized_terminal_failure(monkeypatch):
    recorded = []

    async def interrupted(_autopsy_id):
        raise SoftTimeLimitExceeded()

    async def record(autopsy_id):
        recorded.append(autopsy_id)

    monkeypatch.setattr(task_module, "_run_autopsy_once", interrupted)
    monkeypatch.setattr(task_module, "_record_autopsy_soft_timeout", record)
    task_module._run_autopsy_task_boundary(77)
    assert recorded == [77]
    assert task_module.autopsy_task.soft_time_limit == settings.ai_autopsy_task_soft_limit_seconds
    assert task_module.autopsy_task.time_limit == settings.ai_autopsy_task_hard_limit_seconds
