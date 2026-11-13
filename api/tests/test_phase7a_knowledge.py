from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import Autopsy, Base, Conversion, KnowledgeCandidate, Mapping, Port, ShadowRun, Transformation


WRONG_SQL = "with src as (select amount from source_data) select amount * 0.80 as net_amount from src"
RIGHT_SQL = "with src as (select amount from source_data) select amount * 0.90 as net_amount from src"


def diagnosis():
    return {
        "summary": "The migrated discount expression differs from the PowerCenter mapping.",
        "diagnosis_category": "EXPRESSION_MISMATCH",
        "suspected_root_cause": "EXP_NET uses 0.80 while the source expression requires 0.90.",
        "observed_facts": ["NET_AMOUNT mismatches on corresponding business keys."],
        "hypotheses": ["The expression multiplier was translated incorrectly."],
        "affected_transformations": ["EXP_NET"],
        "affected_columns": ["NET_AMOUNT"],
        "supporting_evidence": [{"reference": "transformations.EXP_NET", "observation": "The mapped expression uses a different multiplier."}],
        "confidence": 95,
        "confidence_reasons": ["Expression structure and comparison metrics align."],
        "suggested_corrective_actions": ["Correct the EXP_NET multiplier and create a new immutable conversion."],
        "suggested_sql": "select amount * 0.90 as net_amount from source_data",
        "risks_and_limitations": ["The suggestion must be independently validated."],
        "recommended_verification_steps": ["Run the corrected conversion on the same fixture."],
        "more_evidence_required": False,
    }


@pytest.fixture
async def knowledge_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            owner_response = await client.post("/api/v1/auth/register", json={"email": "knowledge@example.com", "password": "securepass123"})
            other_response = await client.post("/api/v1/auth/register", json={"email": "other-knowledge@example.com", "password": "securepass123"})
            owner = {"Authorization": f"Bearer {owner_response.json()['access_token']}"}
            other = {"Authorization": f"Bearer {other_response.json()['access_token']}"}
            project = (await client.post("/api/v1/projects", headers=owner, json={"name": "Knowledge Project"})).json()
            isolated_project = (await client.post("/api/v1/projects", headers=owner, json={"name": "Isolated Project"})).json()
            other_project = (await client.post("/api/v1/projects", headers=other, json={"name": "Other Knowledge"})).json()
            async with factory() as db:
                mapping = Mapping(project_id=project["id"], name="m_discount", status="converted")
                isolated_mapping = Mapping(project_id=isolated_project["id"], name="different_name_same_shape", status="converted")
                other_mapping = Mapping(project_id=other_project["id"], name="other_mapping", status="converted")
                db.add_all([mapping, isolated_mapping, other_mapping]); await db.flush()
                for current in (mapping, isolated_mapping, other_mapping):
                    transformation = Transformation(mapping_id=current.id, name="EXP_NET", type="Expression", logic_json={}, seq_order=1)
                    db.add(transformation); await db.flush()
                    db.add(Port(transformation_id=transformation.id, name="NET_AMOUNT", datatype="decimal", direction="OUT", expression="AMOUNT * 0.90"))
                original = Conversion(mapping_id=mapping.id, version=1, generated_sql=WRONG_SQL, confidence_reasons=[], risk_flags=[])
                corrected = Conversion(mapping_id=mapping.id, version=2, generated_sql=RIGHT_SQL, confidence_reasons=[], risk_flags=[])
                db.add_all([original, corrected]); await db.flush()
                fail_run = ShadowRun(
                    project_id=project["id"], mapping_id=mapping.id, conversion_id=original.id,
                    owner_id=owner_response.json()["user"]["id"], fixture_id="orders_discount_v1",
                    status="completed", comparison_result="FAIL", reference_row_count=3,
                    migrated_row_count=3, matched_rows=0, missing_rows=0, unexpected_rows=0,
                    duplicate_key_mismatches=0, column_mismatches=3, null_mismatches=0,
                    numeric_precision_differences=3, mismatch_samples=[], completed_at=datetime.now(timezone.utc),
                )
                db.add(fail_run); await db.flush()
                autopsy = Autopsy(
                    shadow_run_id=fail_run.id, project_id=project["id"], mapping_id=mapping.id,
                    conversion_id=original.id, owner_id=owner_response.json()["user"]["id"],
                    status="completed", diagnosis_category="EXPRESSION_MISMATCH", diagnosis_json=diagnosis(),
                    confidence=95, evidence=diagnosis()["supporting_evidence"],
                    suggested_corrections=diagnosis()["suggested_corrective_actions"],
                    suggested_sql=diagnosis()["suggested_sql"], completed_at=datetime.now(timezone.utc),
                )
                db.add(autopsy); await db.commit()
                ids = {
                    "project": project["id"], "isolated_project": isolated_project["id"],
                    "mapping": mapping.id, "isolated_mapping": isolated_mapping.id,
                    "original": original.id, "corrected": corrected.id, "fail_run": fail_run.id,
                    "autopsy": autopsy.id, "owner": owner_response.json()["user"]["id"],
                }
            yield client, factory, owner, other, ids
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def add_run(factory, ids, *, conversion_id=None, mapping_id=None, project_id=None, fixture="orders_discount_v1", status="completed", result="PASS", mismatches=0, complete=True):
    async with factory() as db:
        run = ShadowRun(
            project_id=project_id or ids["project"], mapping_id=mapping_id or ids["mapping"],
            conversion_id=conversion_id or ids["corrected"], owner_id=ids["owner"], fixture_id=fixture,
            status=status, comparison_result=result, reference_row_count=3, migrated_row_count=3,
            matched_rows=3 if result == "PASS" else 0, missing_rows=0, unexpected_rows=0,
            duplicate_key_mismatches=0, column_mismatches=mismatches, null_mismatches=0,
            numeric_precision_differences=0, mismatch_samples=[],
            completed_at=datetime.now(timezone.utc) if complete else None,
        )
        db.add(run); await db.commit(); await db.refresh(run)
        return run.id


async def create_draft(client, owner, autopsy_id):
    return await client.post(f"/api/v1/autopsies/{autopsy_id}/knowledge-candidates", headers=owner)


@pytest.mark.asyncio
async def test_create_draft_duplicate_and_ownership_without_mutating_history(knowledge_env):
    client, factory, owner, other, ids = knowledge_env
    async with factory() as db:
        before_autopsy = (await db.get(Autopsy, ids["autopsy"])).diagnosis_json.copy()
        before_sql = (await db.get(Conversion, ids["original"])).generated_sql
    assert (await create_draft(client, {}, ids["autopsy"])).status_code == 401
    assert (await create_draft(client, other, ids["autopsy"])).status_code == 404
    response = await create_draft(client, owner, ids["autopsy"])
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft" and body["source_autopsy_id"] == ids["autopsy"]
    assert body["corrected_conversion_id"] is None and [event["event_type"] for event in body["events"]] == ["created"]
    assert (await create_draft(client, owner, ids["autopsy"])).status_code == 409
    assert (await client.get(f"/api/v1/projects/{ids['project']}/knowledge-candidates", headers=other)).status_code == 404
    async with factory() as db:
        assert (await db.get(Autopsy, ids["autopsy"])).diagnosis_json == before_autopsy
        assert (await db.get(Conversion, ids["original"])).generated_sql == before_sql


@pytest.mark.asyncio
async def test_failed_or_incomplete_autopsy_cannot_create_candidate(knowledge_env):
    client, factory, owner, _, ids = knowledge_env
    async with factory() as db:
        incomplete = Autopsy(
            shadow_run_id=ids["fail_run"], project_id=ids["project"], mapping_id=ids["mapping"],
            conversion_id=ids["original"], owner_id=ids["owner"], status="failed",
            evidence=[], suggested_corrections=[], provider_error="provider_request",
        )
        db.add(incomplete); await db.commit(); await db.refresh(incomplete)
    response = await create_draft(client, owner, incomplete.id)
    assert response.status_code == 422 and "completed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_verification_rejects_wrong_provenance_then_accepts_real_fail_to_pass(knowledge_env):
    client, factory, owner, _, ids = knowledge_env
    candidate = (await create_draft(client, owner, ids["autopsy"])).json()
    same_conversion = await add_run(factory, ids, conversion_id=ids["original"])
    wrong_fixture = await add_run(factory, ids, fixture="another_fixture")
    unresolved = await add_run(factory, ids, mismatches=1)
    incomplete = await add_run(factory, ids, complete=False)
    for run_id, expected in (
        (same_conversion, "different immutable conversion"),
        (wrong_fixture, "same test fixture"),
        (unresolved, "unresolved comparison mismatches"),
        (incomplete, "completed with comparison_result=PASS"),
    ):
        response = await client.post(f"/api/v1/knowledge-candidates/{candidate['id']}/verification", headers=owner, json={"passing_shadow_run_id": run_id})
        assert response.status_code == 422 and expected in response.json()["detail"]
    valid_run = await add_run(factory, ids)
    verified = await client.post(f"/api/v1/knowledge-candidates/{candidate['id']}/verification", headers=owner, json={"passing_shadow_run_id": valid_run})
    assert verified.status_code == 200
    body = verified.json()
    assert body["status"] == "verified" and body["verification_scope"] == "Verified on fixture orders_discount_v1"
    assert body["corrected_conversion_id"] == ids["corrected"] and body["corrected_conversion_version"] == 2
    assert [event["event_type"] for event in body["events"]] == ["created", "verified"]


@pytest.mark.asyncio
async def test_rejects_pass_from_unrelated_mapping_and_insufficient_counts(knowledge_env):
    client, factory, owner, _, ids = knowledge_env
    candidate = (await create_draft(client, owner, ids["autopsy"])).json()
    async with factory() as db:
        unrelated_conversion = Conversion(mapping_id=ids["isolated_mapping"], version=1, generated_sql=RIGHT_SQL, confidence_reasons=[], risk_flags=[])
        db.add(unrelated_conversion); await db.commit(); await db.refresh(unrelated_conversion)
    unrelated = await add_run(factory, ids, conversion_id=unrelated_conversion.id, mapping_id=ids["isolated_mapping"], project_id=ids["isolated_project"])
    response = await client.post(f"/api/v1/knowledge-candidates/{candidate['id']}/verification", headers=owner, json={"passing_shadow_run_id": unrelated})
    assert response.status_code == 422 and "same project" in response.json()["detail"]
    insufficient = await add_run(factory, ids)
    async with factory() as db:
        run = await db.get(ShadowRun, insufficient); run.matched_rows = None; await db.commit()
    response = await client.post(f"/api/v1/knowledge-candidates/{candidate['id']}/verification", headers=owner, json={"passing_shadow_run_id": insufficient})
    assert response.status_code == 422 and "row-count provenance" in response.json()["detail"]


@pytest.mark.asyncio
async def test_review_requires_verification_preserves_rejection_and_audit_notes(knowledge_env):
    client, _, owner, _, ids = knowledge_env
    candidate = (await create_draft(client, owner, ids["autopsy"])).json()
    approve = await client.post(f"/api/v1/knowledge-candidates/{candidate['id']}/review", headers=owner, json={"decision": "approve", "notes": "Reviewed evidence."})
    assert approve.status_code == 422 and "verified" in approve.json()["detail"]
    rejected = await client.post(f"/api/v1/knowledge-candidates/{candidate['id']}/review", headers=owner, json={"decision": "reject", "notes": "Correction does not meet review policy."})
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert rejected.json()["review_notes"] == "Correction does not meet review policy."
    assert [event["event_type"] for event in rejected.json()["events"]] == ["created", "reject"]


@pytest.mark.asyncio
async def test_publish_match_rank_project_isolation_and_archive(knowledge_env):
    client, factory, owner, other, ids = knowledge_env
    candidate = (await create_draft(client, owner, ids["autopsy"])).json()
    passing = await add_run(factory, ids)
    await client.post(f"/api/v1/knowledge-candidates/{candidate['id']}/verification", headers=owner, json={"passing_shadow_run_id": passing})
    published = await client.post(f"/api/v1/knowledge-candidates/{candidate['id']}/review", headers=owner, json={"decision": "approve", "notes": "Reviewed corrected SQL and passing validation."})
    assert published.status_code == 200 and published.json()["status"] == "published"
    suggestions = await client.get(f"/api/v1/mappings/{ids['mapping']}/knowledge-suggestions?conversion_id={ids['corrected']}", headers=owner)
    assert suggestions.status_code == 200 and suggestions.json()[0]["knowledge_id"] == candidate["id"]
    assert suggestions.json()[0]["relevance"] in {"HIGH", "MEDIUM"} and suggestions.json()[0]["reasons"]
    assert "does not prove" in suggestions.json()[0]["advisory"]
    assert (await client.get(f"/api/v1/mappings/{ids['isolated_mapping']}/knowledge-suggestions", headers=owner)).json() == []
    assert (await client.get(f"/api/v1/mappings/{ids['mapping']}/knowledge-suggestions", headers=other)).status_code == 404
    archived = await client.post(f"/api/v1/knowledge-candidates/{candidate['id']}/review", headers=owner, json={"decision": "archive", "notes": "Withdrawn after a later platform change."})
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    assert [event["event_type"] for event in archived.json()["events"]] == ["created", "verified", "approve", "archive"]
    assert (await client.get(f"/api/v1/mappings/{ids['mapping']}/knowledge-suggestions", headers=owner)).json() == []
    async with factory() as db:
        assert (await db.scalar(select(KnowledgeCandidate))).status == "archived"
