import io
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.database import get_db
from app.main import app
from app.models import Base
from app.services.powercenter_parser import PowerCenterParseError, parse_powercenter_xml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def phase2_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        async with factory() as session:
            yield session

    previous = settings.parse_tasks_eager
    settings.parse_tasks_eager = True
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        settings.parse_tasks_eager = previous
        app.dependency_overrides.clear()
        await engine.dispose()


async def _user_and_project(client, email="parser@example.com"):
    register = await client.post("/api/v1/auth/register", json={"email": email, "password": "securepass123"})
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    project = await client.post("/api/v1/projects", headers=headers, json={"name": "Parser Project"})
    return headers, project.json()["id"]


@pytest.mark.asyncio
async def test_xml_upload_parses_ports_and_lineage(phase2_client):
    headers, project_id = await _user_and_project(phase2_client)
    xml = (FIXTURES / "expression_filter.xml").read_bytes()
    response = await phase2_client.post(
        f"/api/v1/projects/{project_id}/uploads", headers=headers,
        files={"file": ("expression_filter.xml", xml, "application/xml")},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["uploads"][0]["job_id"]
    job = await phase2_client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job.json()["status"] == "completed"
    mappings = await phase2_client.get(f"/api/v1/projects/{project_id}/mappings", headers=headers)
    assert [item["name"] for item in mappings.json()] == ["m_orders_expression_filter"]
    detail = await phase2_client.get(f"/api/v1/mappings/{mappings.json()[0]['id']}", headers=headers)
    body = detail.json()
    assert [node["type"] for node in body["transformations"]] == [
        "Source Definition", "Expression", "Filter", "Target Definition"
    ]
    net_port = next(
        port for node in body["transformations"] if node["name"] == "EXP_NET"
        for port in node["ports"] if port["name"] == "NET_AMOUNT"
    )
    assert net_port["expression"] == "AMOUNT * 0.90"
    assert len(body["lineage_edges"]) == 6
    assert body["lineage_edges"][0]["from_transformation"] == "SRC_ORDERS"


@pytest.mark.asyncio
async def test_zip_upload_parses_multiple_xml_files(phase2_client):
    headers, project_id = await _user_and_project(phase2_client, "zip@example.com")
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(FIXTURES / "lookup_aggregator.xml", "lookup_aggregator.xml")
        archive.write(FIXTURES / "oracle_null_expression.xml", "nested/oracle_null_expression.xml")
    response = await phase2_client.post(
        f"/api/v1/projects/{project_id}/uploads", headers=headers,
        files={"file": ("mappings.zip", archive_bytes.getvalue(), "application/zip")},
    )
    assert response.status_code == 202, response.text
    assert len(response.json()["uploads"]) == 2
    mappings = (await phase2_client.get(f"/api/v1/projects/{project_id}/mappings", headers=headers)).json()
    assert {item["name"] for item in mappings} == {"m_account_totals", "m_oracle_null_semantics"}


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"<POWERMART><broken>", b"<POWERMART><REPOSITORY/></POWERMART>"])
async def test_malformed_or_missing_mapping_rejected(phase2_client, content):
    headers, project_id = await _user_and_project(phase2_client, f"bad{len(content)}@example.com")
    response = await phase2_client.post(
        f"/api/v1/projects/{project_id}/uploads", headers=headers,
        files={"file": ("bad.xml", content, "application/xml")},
    )
    assert response.status_code == 422
    assert (await phase2_client.get(f"/api/v1/projects/{project_id}/mappings", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_invalid_and_traversal_zip_rejected(phase2_client):
    headers, project_id = await _user_and_project(phase2_client, "unsafe@example.com")
    invalid = await phase2_client.post(
        f"/api/v1/projects/{project_id}/uploads", headers=headers,
        files={"file": ("bad.zip", b"not a zip", "application/zip")},
    )
    assert invalid.status_code == 422
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../escape.xml", (FIXTURES / "expression_filter.xml").read_bytes())
    traversal = await phase2_client.post(
        f"/api/v1/projects/{project_id}/uploads", headers=headers,
        files={"file": ("unsafe.zip", stream.getvalue(), "application/zip")},
    )
    assert traversal.status_code == 422


@pytest.mark.asyncio
async def test_nested_resources_enforce_ownership(phase2_client):
    owner, project_id = await _user_and_project(phase2_client, "owner@example.com")
    other, _ = await _user_and_project(phase2_client, "other@example.com")
    upload = await phase2_client.post(
        f"/api/v1/projects/{project_id}/uploads", headers=owner,
        files={"file": ("mapping.xml", (FIXTURES / "expression_filter.xml").read_bytes(), "application/xml")},
    )
    job_id = upload.json()["uploads"][0]["job_id"]
    mapping_id = (await phase2_client.get(f"/api/v1/projects/{project_id}/mappings", headers=owner)).json()[0]["id"]
    assert (await phase2_client.get(f"/api/v1/projects/{project_id}/mappings", headers=other)).status_code == 404
    assert (await phase2_client.get(f"/api/v1/mappings/{mapping_id}", headers=other)).status_code == 404
    assert (await phase2_client.get(f"/api/v1/jobs/{job_id}", headers=other)).status_code == 404
    assert (await phase2_client.post(
        f"/api/v1/projects/{project_id}/uploads",
        files={"file": ("mapping.xml", b"x", "application/xml")},
    )).status_code == 401


def test_entity_declaration_is_rejected():
    xml = b'<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><POWERMART>&xxe;</POWERMART>'
    with pytest.raises(PowerCenterParseError, match="unsafe"):
        parse_powercenter_xml(xml)
