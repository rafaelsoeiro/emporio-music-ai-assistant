import asyncio

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


async def override_get_db():
    with Session(test_engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


async def request(method: str, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path)


def test_root() -> None:
    response = asyncio.run(request("GET", "/"))

    assert response.status_code == 200
    assert response.json()["name"] == "Emporio Music API"


def test_health_check() -> None:
    response = asyncio.run(request("GET", "/api/v1/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
