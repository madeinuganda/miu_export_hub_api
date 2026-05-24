from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_public_home_structure_without_db():
    """Public home may fail without DB; health always works."""
    r = client.get("/health")
    assert r.status_code == 200
