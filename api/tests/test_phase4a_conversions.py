from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai_service import AIInvocation, AIService, get_ai_service
from app.core.config import settings
from app.core.rate_limit import ai_conversion_limiter
from app.database import get_db
from app.main import app
from app.models import AIUsage, Base, Conversion, LineageEdge, Mapping, Port, Transformation
from app.schemas import ConversionAIOutput, ConversionRiskFlag
from app.services.conversion import detect_conversion_risks

FIXTURES = Path(__file__).parent / "fixtures"


class FakeProvider:
    def __init__(self):
        self.payloads: list[dict] = []

    async def generate(self, system_prompt, payload, output_type):
        assert "one readable CTE per transformation" in system_prompt
        self.payloads.append(payload)
        version_marker = len(self.payloads)
        result = output_type.model_validate({
            "generated_sql": (
                "with src_orders as (select order_id, amount from {{ source('legacy', 'orders') }}),\n"
                "exp_net as (select order_id, amount * 0.90 as net_amount from src_orders),\n"
                "fil_positive as (select * from exp_net where net_amount > 0),\n"
                f"tgt_orders as (select * from fil_positive) select *, {version_marker} as conversion_version from tgt_orders"
            ),
            "schema_yml": "version: 2\nmodels:\n  - name: m_orders_expression_filter\n    description: Converted order mapping\n    columns:\n      - name: order_id\n        description: Order identifier\n",
            "confidence": 91,
            "confidence_reasons": ["All connector endpoints and supported transformations were available."],
            "risk_flags": [{
                "code": "ROUNDING_REVIEW", "severity": "low",
                "message": "Review decimal scale after multiplication.", "transformation": "EXP_NET", "port": "NET_AMOUNT",
            }],
        })
        return AIInvocation(result=result, provider="mock", model_used="mock-claude", input_tokens=120, output_tokens=80)


@pytest.fixture
async def conversion_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    provider = FakeProvider()

    async def override_db():
        async with factory() as session:
            yield session

    previous_eager = settings.parse_tasks_eager
    previous_limit = settings.ai_conversion_rate_limit_per_minute
    settings.parse_tasks_eager = True
    settings.ai_conversion_rate_limit_per_minute = 5
    ai_conversion_limiter.reset()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_ai_service] = lambda: AIService(provider)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, factory, provider
    finally:
        settings.parse_tasks_eager = previous_eager
        settings.ai_conversion_rate_limit_per_minute = previous_limit
        ai_conversion_limiter.reset()
        app.dependency_overrides.clear()
        await engine.dispose()


async def create_mapping(client, email="converter@example.com"):
    registered = await client.post("/api/v1/auth/register", json={"email": email, "password": "securepass123"})
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    project = await client.post("/api/v1/projects", headers=headers, json={"name": "Conversion Project"})
    project_id = project.json()["id"]
    uploaded = await client.post(
        f"/api/v1/projects/{project_id}/uploads", headers=headers,
        files={"file": ("mapping.xml", (FIXTURES / "expression_filter.xml").read_bytes(), "application/xml")},
    )
    assert uploaded.status_code == 202, uploaded.text
    mapping = (await client.get(f"/api/v1/projects/{project_id}/mappings", headers=headers)).json()[0]
    return headers, project_id, mapping["id"]


@pytest.mark.asyncio
async def test_convert_and_regenerate_create_immutable_versions(conversion_env):
    client, factory, provider = conversion_env
    headers, project_id, mapping_id = await create_mapping(client)
    converted = await client.post(f"/api/v1/mappings/{mapping_id}/convert", headers=headers)
    assert converted.status_code == 201, converted.text
    first = converted.json()
    assert first["version"] == 1
    assert first["model_used"] == "mock-claude"
    assert first["confidence"] == 91
    assert first["confidence_reasons"]
    assert first["risk_flags"][0]["code"] == "ROUNDING_REVIEW"

    regenerated = await client.post(
        f"/api/v1/conversions/{first['id']}/regenerate", headers=headers,
        json={"user_comment": "Use a numeric(18,2) cast for net_amount."},
    )
    assert regenerated.status_code == 201, regenerated.text
    second = regenerated.json()
    assert second["version"] == 2 and second["id"] != first["id"]
    assert "numeric(18,2)" in provider.payloads[1]["regeneration"]["user_comment"]
    assert provider.payloads[1]["regeneration"]["previous_version"] == 1

    mapping_payload = provider.payloads[0]["mapping"]
    assert [item["type"] for item in mapping_payload["transformations"]] == [
        "Source Definition", "Expression", "Filter", "Target Definition"
    ]
    assert len(mapping_payload["connectors"]) == 6
    assert all(edge["from"] and edge["to"] for edge in mapping_payload["connectors"])
    assert "raw_xml" not in str(provider.payloads[0])

    async with factory() as session:
        versions = (await session.scalars(select(Conversion).where(Conversion.mapping_id == mapping_id).order_by(Conversion.version))).all()
        usage = (await session.scalars(select(AIUsage).where(AIUsage.project_id == project_id).order_by(AIUsage.id))).all()
        mapping = await session.get(Mapping, mapping_id)
        assert [item.version for item in versions] == [1, 2]
        assert versions[0].generated_sql != versions[1].generated_sql
        assert [(item.operation, item.input_tokens, item.output_tokens) for item in usage] == [
            ("conversion", 120, 80), ("regeneration", 120, 80)
        ]
        assert mapping.status == "converted"


@pytest.mark.asyncio
async def test_conversion_enforces_ownership_and_rate_limit(conversion_env):
    client, _, provider = conversion_env
    owner, _, mapping_id = await create_mapping(client, "owner-convert@example.com")
    other_registration = await client.post("/api/v1/auth/register", json={"email": "other-convert@example.com", "password": "securepass123"})
    other = {"Authorization": f"Bearer {other_registration.json()['access_token']}"}
    assert (await client.post(f"/api/v1/mappings/{mapping_id}/convert", headers=other)).status_code == 404
    assert not provider.payloads
    assert (await client.post(f"/api/v1/mappings/{mapping_id}/convert")).status_code == 401

    settings.ai_conversion_rate_limit_per_minute = 1
    first = await client.post(f"/api/v1/mappings/{mapping_id}/convert", headers=owner)
    assert first.status_code == 201
    limited = await client.post(f"/api/v1/mappings/{mapping_id}/convert", headers=owner)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_missing_ai_configuration_is_safe(conversion_env):
    client, _, _ = conversion_env
    headers, _, mapping_id = await create_mapping(client, "no-ai@example.com")
    app.dependency_overrides[get_ai_service] = lambda: AIService()
    previous_provider = settings.ai_provider
    settings.ai_provider = "gemini"
    try:
        response = await client.post(f"/api/v1/mappings/{mapping_id}/convert", headers=headers)
        assert response.status_code == 503
        assert "GEMINI_API_KEY" in response.json()["detail"]
    finally:
        settings.ai_provider = previous_provider


def test_local_risk_detection_and_generated_sql_validation():
    mapping = Mapping(id=100, project_id=1, name="oracle_risk")
    transformation = Transformation(id=10, mapping_id=100, name="EXP_ORACLE", type="Custom Java", logic_json={}, seq_order=1)
    source = Port(id=1, transformation_id=10, name="SRC_VALUE", datatype="string", direction="IN", expression=None)
    target = Port(id=2, transformation_id=10, name="RESULT", datatype="integer", direction="OUT", expression="NVL(SRC_VALUE, '')")
    transformation.ports = [source, target]
    mapping.transformations = [transformation]
    mapping.lineage_edges = [LineageEdge(mapping_id=100, from_port_id=1, to_port_id=2)]
    codes = {risk.code for risk in detect_conversion_risks(mapping)}
    assert codes == {"UNSUPPORTED_TRANSFORMATION", "ORACLE_SPECIFIC_FUNCTION", "NULL_SEMANTICS", "IMPLICIT_CAST"}

    with pytest.raises(ValueError, match="prohibited"):
        ConversionAIOutput.model_validate({
            "generated_sql": "select * from source; delete from production_table",
            "schema_yml": "version: 2\nmodels: []", "confidence": 10,
            "confidence_reasons": ["Unsafe output"], "risk_flags": [],
        })
