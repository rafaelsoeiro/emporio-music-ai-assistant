from fastapi.testclient import TestClient
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


def override_get_db():
    with Session(test_engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["name"] == "Emporio Music API"


def test_health_check() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
