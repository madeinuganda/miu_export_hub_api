from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_buyer_register_requires_password_confirm():
    r = client.post(
        "/api/v1/auth/buyer/register",
        json={
            "company": "Test Co",
            "first_name": "Test",
            "last_name": "Buyer",
            "email": "newbuyer@test.com",
            "password": "password123",
            "password_confirm": "mismatch",
        },
    )
    assert r.status_code == 422


def test_legacy_unified_login_removed():
    r = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "x"})
    assert r.status_code == 404
