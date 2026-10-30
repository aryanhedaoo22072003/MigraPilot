"""Test working auth, ownership and project CRUD without requiring Docker."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.database import get_db
from app.main import app
from app.models import Base


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_signup_login_and_project_crud(client):
    r = await client.post("/api/v1/auth/register", json={"email": " ENGINEER@EXAMPLE.COM ", "password": "verysecure123"})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    assert r.json()["user"]["email"] == "engineer@example.com"
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/projects")).status_code == 401

    create = await client.post("/api/v1/projects", headers=headers, json={"name": "Finance Migration", "source_system": "powercenter", "target_system": "dbt_postgres"})
    assert create.status_code == 201, create.text
    project_id = create.json()["id"]
    assert len((await client.get("/api/v1/projects", headers=headers)).json()) == 1
    dashboard = await client.get(f"/api/v1/projects/{project_id}/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["total_mappings"] == 0
    assert dashboard.json()["verified_percent"] == 0

    renamed = await client.patch(f"/api/v1/projects/{project_id}", headers=headers, json={"name": "Finance v2"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Finance v2"
    assert (await client.delete(f"/api/v1/projects/{project_id}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/v1/projects/{project_id}", headers=headers)).status_code == 404

    login = await client.post("/api/v1/auth/login", json={"email": "engineer@example.com", "password": "verysecure123"})
    assert login.status_code == 200
    duplicate = await client.post("/api/v1/auth/register", json={"email": "engineer@example.com", "password": "verysecure123"})
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_project_isolation(client):
    users = []
    for email in ("a@example.com", "b@example.com"):
        result = await client.post("/api/v1/auth/register", json={"email": email, "password": "abcdefgh123"})
        users.append({"Authorization": "Bearer " + result.json()["access_token"]})
    result = await client.post("/api/v1/projects", headers=users[0], json={"name": "Sensitive Project"})
    project_id = result.json()["id"]
    assert (await client.get(f"/api/v1/projects/{project_id}", headers=users[1])).status_code == 404
    assert (await client.delete(f"/api/v1/projects/{project_id}", headers=users[1])).status_code == 404
    assert (await client.get("/api/v1/projects", headers=users[1])).json() == []


@pytest.mark.asyncio
async def test_invalid_login_and_validation(client):
    bad = await client.post("/api/v1/auth/register", json={"email": "valid@example.com", "password": "short"})
    assert bad.status_code == 422
    bad_login = await client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong"})
    assert bad_login.status_code == 401
    health = await client.get("/api/v1/health")
    assert health.status_code == 200
